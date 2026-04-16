#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

DEFAULT_TASKS_FILE = Path("ops/continuous/tasks.default.json")
DEFAULT_LOG_DIR = Path("storage/logs/continuous")
ANSI_CSI_PATTERN = re.compile(r"\x1B\[[0-?]*[ -/]*[@-~]")
ANSI_OSC_PATTERN = re.compile(r"\x1B\][^\x1B\x07]*(?:\x07|\x1B\\)")
ANSI_SINGLE_ESCAPE_PATTERN = re.compile(r"\x1B(?:[@-Z\\-_]|[78])")


@dataclass(frozen=True)
class TaskDefinition:
    name: str
    module: str
    cwd: Path
    command: list[str]
    timeout: int | None

    @staticmethod
    def from_dict(raw: dict[str, Any]) -> "TaskDefinition":
        command = raw.get("command")
        if not isinstance(command, list) or not command:
            raise ValueError(f"Invalid task command: {raw}")
        return TaskDefinition(
            name=str(raw["name"]),
            module=str(raw.get("module", "unknown")),
            cwd=Path(str(raw.get("cwd", "."))),
            command=[str(part) for part in command],
            timeout=int(raw["timeout"]) if raw.get("timeout") else None,
        )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run continuous test loops and persist iteration reports."
    )
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument("--tasks-file", type=Path, default=DEFAULT_TASKS_FILE)
    parser.add_argument("--log-dir", type=Path, default=DEFAULT_LOG_DIR)
    parser.add_argument("--interval", type=float, default=60.0)
    parser.add_argument("--max-iterations", type=int, default=0)
    parser.add_argument("--tail-lines", type=int, default=120)
    parser.add_argument("--default-timeout", type=int, default=1200)
    parser.add_argument("--stop-on-failure", action="store_true")
    return parser.parse_args()


def load_tasks(tasks_file: Path) -> list[TaskDefinition]:
    try:
        raw_content = tasks_file.read_text(encoding="utf-8-sig")
    except OSError as err:
        raise ValueError(f"Unable to read tasks file '{tasks_file}': {err}") from err

    try:
        payload = json.loads(raw_content)
    except json.JSONDecodeError as err:
        raise ValueError(
            f"Invalid JSON in tasks file '{tasks_file}': "
            f"{err.msg} (line {err.lineno}, column {err.colno})"
        ) from err

    if not isinstance(payload, dict):
        raise ValueError(f"Invalid tasks file '{tasks_file}': root must be a JSON object.")

    tasks = payload.get("tasks", [])
    if not isinstance(tasks, list):
        raise ValueError(f"Invalid tasks file '{tasks_file}': 'tasks' must be a list.")

    definitions: list[TaskDefinition] = []
    for index, item in enumerate(tasks):
        if not isinstance(item, dict):
            raise ValueError(
                f"Invalid tasks file '{tasks_file}': tasks[{index}] must be a JSON object."
            )
        if not item.get("enabled", True):
            continue
        try:
            definitions.append(TaskDefinition.from_dict(item))
        except (KeyError, TypeError, ValueError) as err:
            raise ValueError(
                f"Invalid task definition in '{tasks_file}' at tasks[{index}]: {err}"
            ) from err

    return definitions


def tail_text(text: str, tail_lines: int) -> str:
    lines = text.splitlines()
    if len(lines) <= tail_lines:
        return text
    return "\n".join(lines[-tail_lines:])


def strip_ansi_sequences(text: str) -> str:
    sanitized = ANSI_OSC_PATTERN.sub("", text)
    sanitized = ANSI_CSI_PATTERN.sub("", sanitized)
    return ANSI_SINGLE_ESCAPE_PATTERN.sub("", sanitized)


def normalize_command(command: list[str]) -> list[str]:
    normalized = list(command)
    if normalized and normalized[0] == "python":
        normalized[0] = sys.executable
    return normalized


def resolve_command(command: list[str]) -> list[str]:
    if not command:
        return command
    executable = command[0]
    if executable == "pnpm":
        pnpm_cmd = shutil.which("pnpm.cmd") or shutil.which("pnpm")
        if pnpm_cmd:
            return [pnpm_cmd, *command[1:]]
        corepack_cmd = shutil.which("corepack.cmd") or shutil.which("corepack")
        if corepack_cmd:
            return [corepack_cmd, "pnpm", *command[1:]]
        return command
    resolved = shutil.which(executable)
    if resolved:
        return [resolved, *command[1:]]
    return command


def run_task(
    task: TaskDefinition,
    repo_root: Path,
    tail_lines: int,
    default_timeout: int,
) -> dict[str, Any]:
    started_at = datetime.now().astimezone().isoformat()
    command = resolve_command(normalize_command(task.command))
    timeout = task.timeout or default_timeout
    started = time.perf_counter()
    try:
        completed = subprocess.run(
            command,
            cwd=repo_root / task.cwd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            check=False,
        )
        status = "passed" if completed.returncode == 0 else "failed"
        stdout_text = strip_ansi_sequences(completed.stdout)
        stderr_text = strip_ansi_sequences(completed.stderr)
        exit_code = completed.returncode
    except FileNotFoundError as err:
        status = "failed"
        stdout_text = ""
        stderr_text = str(err)
        exit_code = 127
    except subprocess.TimeoutExpired as err:
        status = "timeout"
        stdout_text = strip_ansi_sequences(err.stdout or "")
        stderr_text = strip_ansi_sequences(err.stderr or "") + f"\nTask timeout after {timeout}s"
        exit_code = 124
    duration_seconds = round(time.perf_counter() - started, 3)
    return {
        "name": task.name,
        "module": task.module,
        "cwd": str(task.cwd),
        "command": command,
        "status": status,
        "exit_code": exit_code,
        "timeout_seconds": timeout,
        "duration_seconds": duration_seconds,
        "started_at": started_at,
        "finished_at": datetime.now().astimezone().isoformat(),
        "stdout_tail": tail_text(stdout_text, tail_lines),
        "stderr_tail": tail_text(stderr_text, tail_lines),
    }


def build_suggestions(task_results: list[dict[str, Any]]) -> list[str]:
    suggestions: list[str] = []
    for result in task_results:
        if result["status"] == "passed":
            continue
        text = f"{result['stdout_tail']}\n{result['stderr_tail']}"
        name = result["name"]
        if "ModuleNotFoundError" in text or "No module named" in text:
            suggestions.append(f"{name}: install missing Python dependencies.")
        if "No module named 'app'" in text:
            suggestions.append(f"{name}: run benchmark with backend as working directory.")
        if (
            "pnpm" in " ".join(result["command"])
            and ("not recognized" in text or "WinError 2" in text)
        ):
            suggestions.append(f"{name}: install pnpm and rerun frontend tasks.")
        if "FAILED" in text and "pytest" in " ".join(result["command"]):
            suggestions.append(f"{name}: prioritize failing pytest cases and isolate regressions.")
        if result["status"] == "timeout":
            suggestions.append(f"{name}: split suite or increase timeout for unstable long runs.")
    if not suggestions and any(item["duration_seconds"] > 120 for item in task_results):
        suggestions.append("Some tasks are slow; split test suites by module for faster loops.")
    if not suggestions:
        suggestions.append("No new optimization action inferred from this iteration.")
    return sorted(set(suggestions))


def persist_iteration(log_dir: Path, payload: dict[str, Any]) -> Path:
    log_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    path = log_dir / f"iteration-{payload['iteration']:04d}-{stamp}.json"
    content = json.dumps(payload, ensure_ascii=False, indent=2)
    path.write_text(content, encoding="utf-8")
    (log_dir / "latest.json").write_text(content, encoding="utf-8")
    return path


def run_loop(args: argparse.Namespace) -> int:
    repo_root = args.repo_root.resolve()
    tasks_file = args.tasks_file if args.tasks_file.is_absolute() else repo_root / args.tasks_file
    log_dir = args.log_dir if args.log_dir.is_absolute() else repo_root / args.log_dir
    tasks_file = tasks_file.resolve()
    log_dir = log_dir.resolve()

    iteration = 1
    while True:
        try:
            tasks = load_tasks(tasks_file)
        except ValueError as err:
            print(f"Failed to load tasks: {err}", file=sys.stderr)
            return 1
        if not tasks:
            print("No enabled tasks found.")
            return 1

        iteration_started = datetime.now().astimezone().isoformat()
        loop_started = time.perf_counter()
        iteration_results: list[dict[str, Any]] = []
        for task in tasks:
            result = run_task(task, repo_root, args.tail_lines, args.default_timeout)
            iteration_results.append(result)
            print(
                f"[{iteration:04d}] {task.name} => {result['status']} "
                f"({result['duration_seconds']}s)"
            )
            if args.stop_on_failure and result["status"] != "passed":
                break

        failed_count = sum(item["status"] != "passed" for item in iteration_results)
        payload = {
            "iteration": iteration,
            "started_at": iteration_started,
            "tasks_file": str(tasks_file),
            "overall_status": "passed" if failed_count == 0 else "failed",
            "failed_count": failed_count,
            "task_count": len(iteration_results),
            "tasks": iteration_results,
            "optimization_suggestions": build_suggestions(iteration_results),
        }
        report_path = persist_iteration(log_dir, payload)
        print(f"[{iteration:04d}] report => {report_path}")

        if args.max_iterations > 0 and iteration >= args.max_iterations:
            return 0
        if args.stop_on_failure and failed_count > 0:
            return 1

        elapsed = time.perf_counter() - loop_started
        wait_seconds = max(0.0, args.interval - elapsed)
        if wait_seconds > 0:
            time.sleep(wait_seconds)
        iteration += 1


def main() -> int:
    args = parse_args()
    return run_loop(args)


if __name__ == "__main__":
    raise SystemExit(main())
