#!/usr/bin/env python3
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import contextmanager
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Iterator

DEFAULT_TASKS_FILE = Path("ops/continuous/tasks.default.json")
DEFAULT_LOG_DIR = Path("storage/logs/continuous")
DEFAULT_AGENT_NAME = "default"
DEFAULT_AGENT_MODEL = "gpt-5.4"
ITERATION_COUNTER_FILE = ".iteration-counter"
ITERATION_LOCK_FILE = ".iteration-lock"
ANSI_CSI_PATTERN = re.compile(r"\x1B\[[0-?]*[ -/]*[@-~]")
ANSI_OSC_PATTERN = re.compile(r"\x1B\][^\x1B\x07]*(?:\x07|\x1B\\)")
ANSI_SINGLE_ESCAPE_PATTERN = re.compile(r"\x1B(?:[@-Z\\-_]|[78])")
ITERATION_REPORT_PATTERN = re.compile(r"^iteration-(\d+)-\d{8}-\d{6}\.json$")
PERFORMANCE_THRESHOLD_PATTERN = re.compile(r"阈值未达标:\s*(.+)")

if os.name == "nt":
    import msvcrt
else:
    import fcntl


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


def decode_process_output(text: str | bytes | None) -> str:
    if text is None:
        return ""
    if isinstance(text, bytes):
        return text.decode("utf-8", errors="replace")
    return text


def strip_ansi_sequences(text: str | bytes | None) -> str:
    normalized = decode_process_output(text)
    sanitized = ANSI_OSC_PATTERN.sub("", normalized)
    sanitized = ANSI_CSI_PATTERN.sub("", sanitized)
    return ANSI_SINGLE_ESCAPE_PATTERN.sub("", sanitized)


def normalize_command(command: list[str]) -> list[str]:
    normalized = list(command)
    if normalized and normalized[0] == "python":
        normalized[0] = sys.executable
    return normalized


def spawn_task_process(command: list[str], task_cwd: Path) -> subprocess.Popen[str]:
    popen_kwargs: dict[str, Any] = {
        "cwd": task_cwd,
        "stdin": subprocess.DEVNULL,
        "stdout": subprocess.PIPE,
        "stderr": subprocess.PIPE,
        "text": True,
        "encoding": "utf-8",
        "errors": "replace",
    }
    if os.name == "nt":
        popen_kwargs["creationflags"] = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    else:
        popen_kwargs["start_new_session"] = True
    return subprocess.Popen(command, **popen_kwargs)


def force_kill_process(process: subprocess.Popen[str]) -> None:
    try:
        process.kill()
    except (ProcessLookupError, OSError):
        pass


def terminate_process_tree(process: subprocess.Popen[str]) -> None:
    if process.poll() is not None:
        return
    if os.name == "nt":
        try:
            subprocess.run(
                ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                check=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=5,
            )
        except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
            pass
        if process.poll() is None:
            force_kill_process(process)
        return
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        return
    except (PermissionError, OSError):
        force_kill_process(process)


def collect_process_result(
    process: subprocess.Popen[str],
    timeout: int,
) -> tuple[str, str, str, int]:
    try:
        stdout_text, stderr_text = process.communicate(timeout=timeout)
        return (
            "passed" if process.returncode == 0 else "failed",
            strip_ansi_sequences(stdout_text),
            strip_ansi_sequences(stderr_text),
            process.returncode,
        )
    except subprocess.TimeoutExpired as err:
        terminate_process_tree(process)
        try:
            stdout_text, stderr_text = process.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            force_kill_process(process)
            stdout_text, stderr_text = process.communicate()
        stdout_text = strip_ansi_sequences(stdout_text or err.stdout)
        stderr_text = strip_ansi_sequences(stderr_text or err.stderr)
        timeout_message = f"Task timeout after {timeout}s"
        if stderr_text:
            stderr_text = f"{stderr_text}\n{timeout_message}"
        else:
            stderr_text = timeout_message
        return "timeout", stdout_text, stderr_text, 124


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
    if not resolved_cwd.exists():
        raise ValueError(
            f"Task cwd '{task_cwd}' does not exist under repo root '{resolved_repo_root}'."
        )
    if not resolved_cwd.is_dir():
        raise ValueError(
            f"Task cwd '{task_cwd}' is not a directory under repo root '{resolved_repo_root}'."
        )
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
        process = spawn_task_process(command, task_cwd)
    except FileNotFoundError as err:
        status = "failed"
        stdout_text = ""
        stderr_text = str(err)
        exit_code = 127
    else:
        status, stdout_text, stderr_text, exit_code = collect_process_result(process, timeout)
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


def build_lane_failure_result(
    task: TaskDefinition,
    default_timeout: int,
    tail_lines: int,
    reason: str,
) -> dict[str, Any]:
    timestamp = datetime.now().astimezone().isoformat()
    timeout = task.timeout or default_timeout
    stderr_text = strip_ansi_sequences(reason)
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
        "duration_seconds": 0.0,
        "started_at": timestamp,
        "finished_at": timestamp,
        "stdout_tail": "",
        "stderr_tail": tail_text(stderr_text, tail_lines),
    }


def build_lane_failure_results(
    lane: list[tuple[int, TaskDefinition]],
    default_timeout: int,
    tail_lines: int,
    reason: str,
) -> list[tuple[int, TaskDefinition, dict[str, Any]]]:
    return [
        (
            index,
            task,
            build_lane_failure_result(
                task=task,
                default_timeout=default_timeout,
                tail_lines=tail_lines,
                reason=reason,
            ),
        )
        for index, task in lane
    ]


def print_task_result(iteration: int, task_name: str, result: dict[str, Any]) -> None:
    agent_name = str(result.get("agent", DEFAULT_AGENT_NAME))
    print(
        f"[{iteration:04d}] {agent_name}/{task_name} => {result['status']} "
        f"({result['duration_seconds']}s)"
    )


def emit_task_result(iteration: int, task_name: str, result: dict[str, Any]) -> None:
    try:
        print_task_result(iteration, task_name, result)
    except Exception as err:
        try:
            print(
                f"[{iteration:04d}] result logging failed for {task_name}: "
                f"{type(err).__name__}: {err}",
                file=sys.stderr,
            )
        except Exception:
            return


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
    remaining_lane = list(lane)
    while remaining_lane:
        index, task = remaining_lane.pop(0)
        result_recorded = False
        try:
            result = run_task_safe(task, repo_root, tail_lines, default_timeout)
            lane_results.append((index, result))
            result_recorded = True
            emit_task_result(iteration, task.name, result)
        except Exception as err:
            error_text = (
                "Unhandled agent lane error while executing lane: "
                f"{type(err).__name__}: {err}"
            )
            failed_lane = remaining_lane if result_recorded else [(index, task), *remaining_lane]
            for failed_index, failed_task, failed_result in build_lane_failure_results(
                lane=failed_lane,
                default_timeout=default_timeout,
                tail_lines=tail_lines,
                reason=error_text,
            ):
                lane_results.append((failed_index, failed_result))
                emit_task_result(iteration, failed_task.name, failed_result)
            return lane_results
    return lane_results


def merge_lane_results(
    lane: list[tuple[int, TaskDefinition]],
    lane_results: list[tuple[int, dict[str, Any]]],
    ordered_results: list[dict[str, Any] | None],
    default_timeout: int,
    tail_lines: int,
    iteration: int,
) -> None:
    expected_indices = {index for index, _task in lane}
    normalized_results: dict[int, dict[str, Any]] = {}
    for index, result in lane_results:
        if index not in expected_indices:
            raise ValueError(f"Agent lane returned unexpected task index {index}.")
        if index in normalized_results:
            raise ValueError(f"Agent lane returned duplicate task index {index}.")
        normalized_results[index] = result

    for index, result in normalized_results.items():
        ordered_results[index] = result

    missing_lane = [(index, task) for index, task in lane if index not in normalized_results]
    if not missing_lane:
        return

    error_text = (
        "Unhandled agent lane error while awaiting lane results: "
        "lane returned incomplete results."
    )
    for index, task, failed_result in build_lane_failure_results(
        lane=missing_lane,
        default_timeout=default_timeout,
        tail_lines=tail_lines,
        reason=error_text,
    ):
        ordered_results[index] = failed_result
        emit_task_result(iteration, task.name, failed_result)


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
        emit_task_result(iteration, task.name, result)
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
                emit_task_result(iteration, skipped_task.name, skipped_result)
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
            lane = futures[future]
            try:
                lane_results = future.result()
                merge_lane_results(
                    lane=lane,
                    lane_results=lane_results,
                    ordered_results=ordered_results,
                    default_timeout=default_timeout,
                    tail_lines=tail_lines,
                    iteration=iteration,
                )
            except Exception as err:
                error_text = (
                    "Unhandled agent lane error while awaiting lane results: "
                    f"{type(err).__name__}: {err}"
                )
                for index, task, failed_result in build_lane_failure_results(
                    lane=lane,
                    default_timeout=default_timeout,
                    tail_lines=tail_lines,
                    reason=error_text,
                ):
                    if ordered_results[index] is not None:
                        continue
                    ordered_results[index] = failed_result
                    emit_task_result(iteration, task.name, failed_result)
                continue
    return [result for result in ordered_results if result is not None]


def command_tokens(command: Any) -> list[str]:
    if not isinstance(command, list):
        return []
    tokens: list[str] = []
    for part in command:
        text = str(part).strip()
        if text:
            tokens.append(Path(text).name.lower())
    return tokens


def command_contains_executable(command: Any, executable: str) -> bool:
    if not isinstance(command, list):
        return False
    expected = executable.lower()
    for part in command:
        text = str(part).strip()
        if text and Path(text).stem.lower() == expected:
            return True
    return False


def is_missing_executable_error(text: str) -> bool:
    lower_text = text.lower()
    return "winerror 2" in lower_text or "no such file or directory" in lower_text


def infer_frontend_suggestion(result: dict[str, Any], text: str) -> str | None:
    if str(result.get("module", "")).strip() != "frontend":
        return None
    name = result["name"]
    tokens = command_tokens(result.get("command"))
    lower_text = text.lower()
    if "lint:check" in tokens:
        return f"{name}: fix the reported ESLint violations in frontend sources before rerunning."
    if "format:check" in tokens:
        return f"{name}: apply formatter changes for the reported frontend files before rerunning."
    if "test:coverage" in tokens or "coverage.enabled" in tokens:
        if "coverage" in lower_text and "threshold" in lower_text:
            return (
                f"{name}: raise frontend coverage or narrow the intended coverage scope "
                "before rerunning."
            )
        return f"{name}: fix the failing frontend test cases before rerunning."
    if "test" in tokens:
        return f"{name}: fix the failing frontend test cases before rerunning."
    if "build" in tokens:
        return f"{name}: fix the reported frontend build errors before rerunning."
    return None


def infer_performance_suggestion(result: dict[str, Any], text: str) -> str | None:
    if str(result.get("module", "")).strip() != "performance":
        return None

    match = PERFORMANCE_THRESHOLD_PATTERN.search(text)
    if not match:
        return None

    metrics = [item.strip() for item in match.group(1).split(",") if item.strip()]
    name = result["name"]
    if metrics:
        return (
            f"{name}: investigate breached performance thresholds: "
            f"{', '.join(metrics)}."
        )
    return f"{name}: investigate the reported performance threshold breaches."


def build_suggestions(task_results: list[dict[str, Any]]) -> list[str]:
    suggestions: list[str] = []
    for result in task_results:
        if result["status"] in {"passed", "skipped"}:
            continue
        text = f"{result['stdout_tail']}\n{result['stderr_tail']}"
        name = result["name"]
        resolved_command = " ".join(str(part) for part in result["command"])
        if (
            "Task cwd '" in text
            and "repo root" in text
            and (
                "escapes repo root" in text
                or "does not exist under repo root" in text
                or "is not a directory under repo root" in text
            )
        ):
            suggestions.append(
                f"{name}: fix task.cwd to an existing directory under repo_root."
            )
        if "ModuleNotFoundError" in text or "No module named" in text:
            suggestions.append(f"{name}: install missing Python dependencies.")
        if "No module named 'app'" in text:
            suggestions.append(f"{name}: run benchmark with backend as working directory.")
        missing_pnpm = (
            result.get("exit_code") == 127
            and command_contains_executable(result.get("command"), "pnpm")
            and is_missing_executable_error(text)
        )
        if missing_pnpm:
            suggestions.append(f"{name}: install pnpm and rerun frontend tasks.")
        frontend_suggestion = None if missing_pnpm else infer_frontend_suggestion(result, text)
        if frontend_suggestion:
            suggestions.append(frontend_suggestion)
        performance_suggestion = infer_performance_suggestion(result, text)
        if performance_suggestion:
            suggestions.append(performance_suggestion)
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


def infer_next_iteration_from_history(log_dir: Path) -> int | None:
    highest_iteration = 0
    for candidate in log_dir.glob("iteration-*.json"):
        if not candidate.is_file():
            continue
        match = ITERATION_REPORT_PATTERN.match(candidate.name)
        if not match:
            continue
        iteration = int(match.group(1))
        if iteration > highest_iteration:
            highest_iteration = iteration
    if highest_iteration > 0:
        return highest_iteration + 1
    return None


def infer_next_iteration(log_dir: Path) -> int:
    history_next = infer_next_iteration_from_history(log_dir)
    latest_path = log_dir / "latest.json"
    try:
        raw_content = latest_path.read_text(encoding="utf-8")
    except OSError:
        return history_next or 1
    try:
        payload = json.loads(raw_content)
    except json.JSONDecodeError:
        return history_next or 1
    if not isinstance(payload, dict):
        return history_next or 1
    iteration = payload.get("iteration")
    if type(iteration) is int and iteration > 0:
        next_iteration = iteration + 1
        if history_next is not None:
            return max(next_iteration, history_next)
        return next_iteration
    return history_next or 1


def _ensure_lock_file_bytes(handle: Any) -> None:
    handle.seek(0, os.SEEK_END)
    if handle.tell() == 0:
        handle.write(b"0")
        handle.flush()
    handle.seek(0)


def _lock_file(handle: Any) -> None:
    _ensure_lock_file_bytes(handle)
    if os.name == "nt":
        while True:
            try:
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                return
            except OSError as exc:
                if getattr(exc, "winerror", None) not in {33, 36} and getattr(exc, "errno", None) != 13:
                    raise
                time.sleep(0.01)
    fcntl.flock(handle.fileno(), fcntl.LOCK_EX)


def _unlock_file(handle: Any) -> None:
    handle.seek(0)
    if os.name == "nt":
        msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
        return
    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


@contextmanager
def _lock_iteration_state(log_dir: Path) -> Iterator[None]:
    log_dir.mkdir(parents=True, exist_ok=True)
    lock_path = log_dir / ITERATION_LOCK_FILE
    with lock_path.open("a+b") as handle:
        _lock_file(handle)
        try:
            yield
        finally:
            _unlock_file(handle)


def _read_reserved_iteration(log_dir: Path) -> int:
    counter_path = log_dir / ITERATION_COUNTER_FILE
    try:
        raw_value = counter_path.read_text(encoding="utf-8").strip()
    except OSError:
        return 0
    if raw_value.isdigit():
        iteration = int(raw_value)
        if iteration > 0:
            return iteration
    return 0


def reserve_next_iteration(log_dir: Path) -> int:
    with _lock_iteration_state(log_dir):
        next_from_reports = infer_next_iteration(log_dir)
        last_reserved = _read_reserved_iteration(log_dir)
        reserved_iteration = max(next_from_reports, last_reserved + 1)
        (log_dir / ITERATION_COUNTER_FILE).write_text(
            str(reserved_iteration),
            encoding="utf-8",
        )
        return reserved_iteration


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
        try:
            iteration = reserve_next_iteration(log_dir)
        except OSError as err:
            print(f"Failed to reserve iteration id: {err}", file=sys.stderr)
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


def main() -> int:
    args = parse_args()
    return run_loop(args)


if __name__ == "__main__":
    raise SystemExit(main())
