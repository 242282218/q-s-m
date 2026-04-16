#!/usr/bin/env python3
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
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
DEFAULT_AGENT_NAME = "default"
DEFAULT_AGENT_MODEL = "gpt-5.3-codex"
ANSI_CSI_PATTERN = re.compile(r"\x1B\[[0-?]*[ -/]*[@-~]")
ANSI_OSC_PATTERN = re.compile(r"\x1B\][^\x1B\x07]*(?:\x07|\x1B\\)")
ANSI_SINGLE_ESCAPE_PATTERN = re.compile(r"\x1B(?:[@-Z\\-_]|[78])")


def parse_agent(raw: Any) -> tuple[str, str]:
    if raw is None:
        return DEFAULT_AGENT_NAME, DEFAULT_AGENT_MODEL
    if not isinstance(raw, dict):
        raise ValueError("Task field 'agent' must be a JSON object.")

    unknown_fields = sorted(set(raw) - {"name", "model"})
    if unknown_fields:
        unknown_list = ", ".join(unknown_fields)
        raise ValueError(
            f"Task field 'agent' only supports keys 'name' and 'model' (got: {unknown_list})."
        )

    name = raw.get("name", DEFAULT_AGENT_NAME)
    if not isinstance(name, str) or not name.strip():
        raise ValueError("Task field 'agent.name' must be a non-empty string.")

    model = raw.get("model", DEFAULT_AGENT_MODEL)
    if not isinstance(model, str) or not model.strip():
        raise ValueError("Task field 'agent.model' must be a non-empty string.")
    if model.strip() != DEFAULT_AGENT_MODEL:
        raise ValueError(f"Task field 'agent.model' must be '{DEFAULT_AGENT_MODEL}'.")

    return name.strip(), model.strip()


@dataclass(frozen=True)
class TaskDefinition:
    name: str
    module: str
    cwd: Path
    command: list[str]
    timeout: int | None
    agent: str = DEFAULT_AGENT_NAME
    model: str = DEFAULT_AGENT_MODEL

    @staticmethod
    def from_dict(raw: dict[str, Any]) -> "TaskDefinition":
        command = raw.get("command")
        if not isinstance(command, list) or not command:
            raise ValueError(f"Invalid task command: {raw}")
        normalized_command: list[str] = []
        for part in command:
            if not isinstance(part, str) or not part.strip():
                raise ValueError("Task field 'command' must be a non-empty string array.")
            normalized_command.append(part)
        name = raw.get("name")
        module = raw.get("module", "unknown")
        cwd = raw.get("cwd", ".")
        if not isinstance(name, str) or not name.strip():
            raise ValueError("Task field 'name' must be a non-empty string.")
        if not isinstance(module, str) or not module.strip():
            raise ValueError("Task field 'module' must be a non-empty string.")
        if not isinstance(cwd, str) or not cwd.strip():
            raise ValueError("Task field 'cwd' must be a non-empty string.")
        timeout_raw = raw.get("timeout")
        if timeout_raw is None:
            timeout = None
        elif isinstance(timeout_raw, int) and not isinstance(timeout_raw, bool) and timeout_raw > 0:
            timeout = timeout_raw
        else:
            raise ValueError("Task field 'timeout' must be a positive integer.")
        agent, model = parse_agent(raw.get("agent"))
        return TaskDefinition(
            name=name.strip(),
            module=module.strip(),
            cwd=Path(cwd.strip()),
            command=normalized_command,
            timeout=timeout,
            agent=agent,
            model=model,
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
    parser.add_argument("--max-workers", type=int, default=1)
    parser.add_argument("--stop-on-failure", action="store_true")
    return parser.parse_args()


def validate_runtime_args(args: argparse.Namespace) -> tuple[float, int, int, int, int]:
    interval_raw = getattr(args, "interval", 60.0)
    if isinstance(interval_raw, bool) or not isinstance(interval_raw, (int, float)):
        raise ValueError("Argument 'interval' must be a non-negative number.")
    interval = float(interval_raw)
    if interval < 0:
        raise ValueError("Argument 'interval' must be a non-negative number.")

    max_iterations = getattr(args, "max_iterations", 0)
    if type(max_iterations) is not int or max_iterations < 0:
        raise ValueError("Argument 'max_iterations' must be a non-negative integer.")

    tail_lines = getattr(args, "tail_lines", 120)
    if type(tail_lines) is not int or tail_lines <= 0:
        raise ValueError("Argument 'tail_lines' must be a positive integer.")

    default_timeout = getattr(args, "default_timeout", 1200)
    if type(default_timeout) is not int or default_timeout <= 0:
        raise ValueError("Argument 'default_timeout' must be a positive integer.")

    max_workers = getattr(args, "max_workers", 1)
    if type(max_workers) is not int or max_workers <= 0:
        raise ValueError("Argument 'max_workers' must be a positive integer.")

    return interval, max_iterations, tail_lines, default_timeout, max_workers


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

    if "tasks" not in payload:
        raise ValueError(f"Invalid tasks file '{tasks_file}': missing required 'tasks' field.")
    unknown_root_fields = sorted(set(payload) - {"tasks"})
    if unknown_root_fields:
        unknown_list = ", ".join(unknown_root_fields)
        raise ValueError(
            f"Invalid tasks file '{tasks_file}': root has unsupported fields: {unknown_list}."
        )

    tasks = payload["tasks"]
    if not isinstance(tasks, list):
        raise ValueError(f"Invalid tasks file '{tasks_file}': 'tasks' must be a list.")

    definitions: list[TaskDefinition] = []
    seen_names: set[str] = set()
    allowed_task_fields = {"name", "module", "cwd", "command", "timeout", "enabled", "agent"}
    for index, item in enumerate(tasks):
        if not isinstance(item, dict):
            raise ValueError(
                f"Invalid tasks file '{tasks_file}': tasks[{index}] must be a JSON object."
            )
        unknown_fields = sorted(set(item) - allowed_task_fields)
        if unknown_fields:
            unknown_list = ", ".join(unknown_fields)
            raise ValueError(
                f"Invalid tasks file '{tasks_file}': tasks[{index}] has unsupported fields: "
                f"{unknown_list}."
            )
        enabled = item.get("enabled", True)
        if not isinstance(enabled, bool):
            raise ValueError(
                f"Invalid tasks file '{tasks_file}': tasks[{index}].enabled must be a boolean."
            )
        try:
            definition = TaskDefinition.from_dict(item)
        except (KeyError, TypeError, ValueError) as err:
            raise ValueError(
                f"Invalid task definition in '{tasks_file}' at tasks[{index}]: {err}"
            ) from err
        if definition.name in seen_names:
            raise ValueError(
                f"Invalid tasks file '{tasks_file}': duplicate task name "
                f"'{definition.name}' at tasks[{index}]."
            )
        seen_names.add(definition.name)
        if enabled:
            definitions.append(definition)

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


def resolve_task_cwd(repo_root: Path, task_cwd: Path) -> Path:
    resolved_repo_root = repo_root.resolve()
    candidate = task_cwd if task_cwd.is_absolute() else resolved_repo_root / task_cwd
    resolved_cwd = candidate.resolve()
    try:
        resolved_cwd.relative_to(resolved_repo_root)
    except ValueError as err:
        raise ValueError(
            f"Task cwd '{task_cwd}' escapes repo root '{resolved_repo_root}'."
        ) from err
    return resolved_cwd


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
        task_cwd = resolve_task_cwd(repo_root, task.cwd)
    except ValueError as err:
        duration_seconds = round(time.perf_counter() - started, 3)
        stderr_text = strip_ansi_sequences(str(err))
        return {
            "name": task.name,
            "module": task.module,
            "agent": task.agent,
            "model": task.model,
            "cwd": str(task.cwd),
            "command": command,
            "status": "failed",
            "exit_code": 78,
            "timeout_seconds": timeout,
            "duration_seconds": duration_seconds,
            "started_at": started_at,
            "finished_at": datetime.now().astimezone().isoformat(),
            "stdout_tail": "",
            "stderr_tail": tail_text(stderr_text, tail_lines),
        }
    try:
        completed = subprocess.run(
            command,
            cwd=task_cwd,
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
        "agent": task.agent,
        "model": task.model,
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


def run_task_safe(
    task: TaskDefinition,
    repo_root: Path,
    tail_lines: int,
    default_timeout: int,
) -> dict[str, Any]:
    started_at = datetime.now().astimezone().isoformat()
    started = time.perf_counter()
    try:
        return run_task(task, repo_root, tail_lines, default_timeout)
    except Exception as err:
        duration_seconds = round(time.perf_counter() - started, 3)
        timeout = task.timeout or default_timeout
        stderr_text = strip_ansi_sequences(
            f"Unhandled task runner error: {type(err).__name__}: {err}"
        )
        return {
            "name": task.name,
            "module": task.module,
            "agent": task.agent,
            "model": task.model,
            "cwd": str(task.cwd),
            "command": resolve_command(normalize_command(task.command)),
            "status": "failed",
            "exit_code": 70,
            "timeout_seconds": timeout,
            "duration_seconds": duration_seconds,
            "started_at": started_at,
            "finished_at": datetime.now().astimezone().isoformat(),
            "stdout_tail": "",
            "stderr_tail": tail_text(stderr_text, tail_lines),
        }


def build_skipped_task_result(
    task: TaskDefinition,
    default_timeout: int,
    reason: str,
) -> dict[str, Any]:
    timestamp = datetime.now().astimezone().isoformat()
    return {
        "name": task.name,
        "module": task.module,
        "agent": task.agent,
        "model": task.model,
        "cwd": str(task.cwd),
        "command": resolve_command(normalize_command(task.command)),
        "status": "skipped",
        "exit_code": 125,
        "timeout_seconds": task.timeout or default_timeout,
        "duration_seconds": 0.0,
        "started_at": timestamp,
        "finished_at": timestamp,
        "stdout_tail": "",
        "stderr_tail": reason,
    }


def print_task_result(iteration: int, task_name: str, result: dict[str, Any]) -> None:
    agent_name = str(result.get("agent", DEFAULT_AGENT_NAME))
    print(
        f"[{iteration:04d}] {agent_name}/{task_name} => {result['status']} "
        f"({result['duration_seconds']}s)"
    )


def build_agent_lanes(
    tasks: list[TaskDefinition],
) -> list[list[tuple[int, TaskDefinition]]]:
    lanes: dict[str, list[tuple[int, TaskDefinition]]] = {}
    for index, task in enumerate(tasks):
        lanes.setdefault(task.agent, []).append((index, task))
    return list(lanes.values())


def run_agent_lane(
    lane: list[tuple[int, TaskDefinition]],
    repo_root: Path,
    tail_lines: int,
    default_timeout: int,
    iteration: int,
) -> list[tuple[int, dict[str, Any]]]:
    lane_results: list[tuple[int, dict[str, Any]]] = []
    for index, task in lane:
        result = run_task_safe(task, repo_root, tail_lines, default_timeout)
        lane_results.append((index, result))
        print_task_result(iteration, task.name, result)
    return lane_results


def run_tasks_sequential(
    tasks: list[TaskDefinition],
    repo_root: Path,
    tail_lines: int,
    default_timeout: int,
    iteration: int,
    stop_on_failure: bool,
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for index, task in enumerate(tasks):
        result = run_task_safe(task, repo_root, tail_lines, default_timeout)
        results.append(result)
        print_task_result(iteration, task.name, result)
        if stop_on_failure and result["status"] != "passed":
            skipped_reason = (
                "Skipped because stop-on-failure halted the iteration after "
                "a previous task failed."
            )
            for skipped_task in tasks[index + 1 :]:
                skipped_result = build_skipped_task_result(
                    skipped_task,
                    default_timeout,
                    skipped_reason,
                )
                results.append(skipped_result)
                print_task_result(iteration, skipped_task.name, skipped_result)
            break
    return results


def run_tasks_parallel(
    tasks: list[TaskDefinition],
    repo_root: Path,
    tail_lines: int,
    default_timeout: int,
    iteration: int,
    max_workers: int,
) -> list[dict[str, Any]]:
    ordered_results: list[dict[str, Any] | None] = [None] * len(tasks)
    lanes = build_agent_lanes(tasks)
    worker_count = min(max_workers, len(lanes))
    with ThreadPoolExecutor(max_workers=worker_count) as executor:
        futures = {
            executor.submit(
                run_agent_lane,
                lane,
                repo_root,
                tail_lines,
                default_timeout,
                iteration,
            ): lane
            for lane in lanes
        }
        for future in as_completed(futures):
            for index, result in future.result():
                ordered_results[index] = result
    return [result for result in ordered_results if result is not None]


def build_suggestions(task_results: list[dict[str, Any]]) -> list[str]:
    suggestions: list[str] = []
    for result in task_results:
        if result["status"] in {"passed", "skipped"}:
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


def build_agent_summary(task_results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    summary_by_agent: dict[str, dict[str, Any]] = {}
    ordered_agents: list[str] = []
    for result in task_results:
        agent = str(result.get("agent", DEFAULT_AGENT_NAME))
        model = str(result.get("model", DEFAULT_AGENT_MODEL))
        if agent not in summary_by_agent:
            summary_by_agent[agent] = {
                "agent": agent,
                "model": model,
                "task_count": 0,
                "failed_count": 0,
                "total_duration_seconds": 0.0,
            }
            ordered_agents.append(agent)
        item = summary_by_agent[agent]
        item["task_count"] += 1
        if result["status"] not in {"passed", "skipped"}:
            item["failed_count"] += 1
        item["total_duration_seconds"] += float(result["duration_seconds"])

    for agent in ordered_agents:
        total = float(summary_by_agent[agent]["total_duration_seconds"])
        summary_by_agent[agent]["total_duration_seconds"] = round(total, 3)
    return [summary_by_agent[agent] for agent in ordered_agents]


def persist_iteration(log_dir: Path, payload: dict[str, Any]) -> Path:
    log_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    path = log_dir / f"iteration-{payload['iteration']:04d}-{stamp}.json"
    content = json.dumps(payload, ensure_ascii=False, indent=2)
    path.write_text(content, encoding="utf-8")
    (log_dir / "latest.json").write_text(content, encoding="utf-8")
    return path


def infer_next_iteration(log_dir: Path) -> int:
    latest_path = log_dir / "latest.json"
    try:
        raw_content = latest_path.read_text(encoding="utf-8")
    except OSError:
        return 1
    try:
        payload = json.loads(raw_content)
    except json.JSONDecodeError:
        return 1
    if not isinstance(payload, dict):
        return 1
    iteration = payload.get("iteration")
    if type(iteration) is int and iteration > 0:
        return iteration + 1
    return 1


def run_loop(args: argparse.Namespace) -> int:
    try:
        interval, max_iterations, tail_lines, default_timeout, max_workers = (
            validate_runtime_args(args)
        )
    except ValueError as err:
        print(f"Invalid runtime arguments: {err}", file=sys.stderr)
        return 1

    repo_root = args.repo_root.resolve()
    tasks_file = args.tasks_file if args.tasks_file.is_absolute() else repo_root / args.tasks_file
    log_dir = args.log_dir if args.log_dir.is_absolute() else repo_root / args.log_dir
    tasks_file = tasks_file.resolve()
    log_dir = log_dir.resolve()
    if args.stop_on_failure and max_workers > 1:
        print(
            "stop-on-failure is enabled; forcing max-workers=1 for deterministic fail-fast.",
            file=sys.stderr,
        )
        max_workers = 1

    iteration = infer_next_iteration(log_dir)
    executed_iterations = 0
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
        if max_workers == 1:
            iteration_results = run_tasks_sequential(
                tasks=tasks,
                repo_root=repo_root,
                tail_lines=tail_lines,
                default_timeout=default_timeout,
                iteration=iteration,
                stop_on_failure=args.stop_on_failure,
            )
        else:
            iteration_results = run_tasks_parallel(
                tasks=tasks,
                repo_root=repo_root,
                tail_lines=tail_lines,
                default_timeout=default_timeout,
                iteration=iteration,
                max_workers=max_workers,
            )

        failed_count = sum(
            item["status"] not in {"passed", "skipped"} for item in iteration_results
        )
        agent_summary = build_agent_summary(iteration_results)
        payload = {
            "iteration": iteration,
            "started_at": iteration_started,
            "tasks_file": str(tasks_file),
            "overall_status": "passed" if failed_count == 0 else "failed",
            "failed_count": failed_count,
            "task_count": len(iteration_results),
            "agent_count": len(agent_summary),
            "agents": agent_summary,
            "tasks": iteration_results,
            "optimization_suggestions": build_suggestions(iteration_results),
        }
        try:
            report_path = persist_iteration(log_dir, payload)
        except OSError as err:
            print(f"Failed to persist iteration report: {err}", file=sys.stderr)
            return 1
        print(f"[{iteration:04d}] report => {report_path}")

        executed_iterations += 1
        if args.stop_on_failure and failed_count > 0:
            return 1
        if max_iterations > 0 and executed_iterations >= max_iterations:
            return 0

        elapsed = time.perf_counter() - loop_started
        wait_seconds = max(0.0, interval - elapsed)
        if wait_seconds > 0:
            time.sleep(wait_seconds)
        iteration += 1


def main() -> int:
    args = parse_args()
    return run_loop(args)


if __name__ == "__main__":
    raise SystemExit(main())
