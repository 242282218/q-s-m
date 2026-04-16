import io
import json
from argparse import Namespace
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ops.continuous.continuous_runner import (
    DEFAULT_TASKS_FILE,
    TaskDefinition,
    load_tasks,
    run_loop,
    run_task,
)


class ContinuousRunnerTaskFileTests(unittest.TestCase):
    @staticmethod
    def _passed_result(name: str) -> dict[str, object]:
        return {
            "name": name,
            "module": "test",
            "cwd": ".",
            "command": ["python", "-m", "pytest"],
            "status": "passed",
            "exit_code": 0,
            "timeout_seconds": 30,
            "duration_seconds": 0.01,
            "started_at": "2026-01-01T00:00:00+00:00",
            "finished_at": "2026-01-01T00:00:01+00:00",
            "stdout_tail": "",
            "stderr_tail": "",
        }

    def test_default_tasks_cover_quality_and_performance_gates(self):
        tasks = load_tasks(ROOT / DEFAULT_TASKS_FILE)
        tasks_by_name = {task.name: task for task in tasks}

        self.assertTrue(
            {
                "backend_pytest",
                "frontend_lint_fix",
                "frontend_vitest",
                "frontend_build",
                "performance_benchmark",
            }.issubset(tasks_by_name)
        )
        frontend_build = tasks_by_name["frontend_build"]
        self.assertEqual(frontend_build.cwd, Path("frontend"))
        self.assertEqual(frontend_build.command, ["pnpm", "build"])
        self.assertEqual(frontend_build.timeout, 900)

        performance_task = tasks_by_name["performance_benchmark"]
        self.assertEqual(performance_task.cwd, Path("backend"))
        self.assertEqual(
            performance_task.command,
            ["python", "../tests/performance/benchmark.py", "--output-json"],
        )

    def test_load_tasks_supports_utf8_bom(self):
        payload = {
            "tasks": [
                {
                    "name": "backend_pytest",
                    "module": "backend",
                    "cwd": "backend",
                    "command": ["python", "-m", "pytest"],
                    "timeout": 1800,
                    "enabled": True,
                }
            ]
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            tasks_file = Path(temp_dir) / "tasks.bom.json"
            tasks_file.write_text(
                json.dumps(payload, ensure_ascii=False),
                encoding="utf-8-sig",
            )
            tasks = load_tasks(tasks_file)

        self.assertEqual(len(tasks), 1)
        self.assertEqual(tasks[0].name, "backend_pytest")
        self.assertEqual(tasks[0].cwd, Path("backend"))
        self.assertEqual(tasks[0].command, ["python", "-m", "pytest"])

    def test_load_tasks_reports_missing_file(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            missing_file = Path(temp_dir) / "missing.tasks.json"
            with self.assertRaisesRegex(ValueError, r"Unable to read tasks file"):
                load_tasks(missing_file)

    def test_load_tasks_rejects_non_list_tasks_field(self):
        payload = {"tasks": {"name": "invalid"}}

        with tempfile.TemporaryDirectory() as temp_dir:
            tasks_file = Path(temp_dir) / "tasks.invalid.json"
            tasks_file.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, r"'tasks' must be a list"):
                load_tasks(tasks_file)

    def test_load_tasks_rejects_non_object_task_item(self):
        payload = {"tasks": ["invalid-item"]}

        with tempfile.TemporaryDirectory() as temp_dir:
            tasks_file = Path(temp_dir) / "tasks.invalid.json"
            tasks_file.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaisesRegex(
                ValueError, r"tasks\[0\] must be a JSON object"
            ):
                load_tasks(tasks_file)

    def test_load_tasks_reports_task_index_for_invalid_definition(self):
        payload = {
            "tasks": [
                {
                    "name": "bad_task",
                    "module": "backend",
                    "cwd": "backend",
                    "command": "python -m pytest",
                }
            ]
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            tasks_file = Path(temp_dir) / "tasks.invalid.json"
            tasks_file.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaisesRegex(
                ValueError, r"tasks\[0\]: Invalid task command"
            ):
                load_tasks(tasks_file)

    def test_run_loop_returns_error_for_invalid_tasks_file_schema(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            repo_root = Path(temp_dir)
            tasks_file = repo_root / "tasks.invalid.json"
            tasks_file.write_text(json.dumps({"tasks": {}}), encoding="utf-8")
            args = Namespace(
                repo_root=repo_root,
                tasks_file=tasks_file,
                log_dir=repo_root / "logs",
                interval=1.0,
                max_iterations=1,
                tail_lines=20,
                default_timeout=30,
                stop_on_failure=False,
            )
            exit_code = run_loop(args)

        self.assertEqual(exit_code, 1)

    def test_run_loop_returns_error_for_missing_tasks_file(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            repo_root = Path(temp_dir)
            tasks_file = repo_root / "missing.tasks.json"
            args = Namespace(
                repo_root=repo_root,
                tasks_file=tasks_file,
                log_dir=repo_root / "logs",
                interval=1.0,
                max_iterations=1,
                tail_lines=20,
                default_timeout=30,
                stop_on_failure=False,
            )
            exit_code = run_loop(args)

        self.assertEqual(exit_code, 1)

    def test_run_loop_reload_tasks_every_iteration(self):
        task = TaskDefinition(
            name="dynamic_task",
            module="test",
            cwd=Path("."),
            command=["python", "-m", "pytest"],
            timeout=30,
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            repo_root = Path(temp_dir)
            args = Namespace(
                repo_root=repo_root,
                tasks_file=repo_root / "tasks.json",
                log_dir=repo_root / "logs",
                interval=0.0,
                max_iterations=2,
                tail_lines=20,
                default_timeout=30,
                stop_on_failure=False,
            )

            with (
                patch(
                    "ops.continuous.continuous_runner.load_tasks",
                    side_effect=[[task], [task]],
                ) as load_tasks_mock,
                patch(
                    "ops.continuous.continuous_runner.run_task",
                    return_value=self._passed_result("dynamic_task"),
                ),
                patch(
                    "ops.continuous.continuous_runner.persist_iteration",
                    return_value=repo_root / "report.json",
                ),
            ):
                exit_code = run_loop(args)

        self.assertEqual(exit_code, 0)
        self.assertEqual(load_tasks_mock.call_count, 2)

    def test_run_loop_returns_error_when_task_reload_fails_midway(self):
        task = TaskDefinition(
            name="dynamic_task",
            module="test",
            cwd=Path("."),
            command=["python", "-m", "pytest"],
            timeout=30,
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            repo_root = Path(temp_dir)
            args = Namespace(
                repo_root=repo_root,
                tasks_file=repo_root / "tasks.json",
                log_dir=repo_root / "logs",
                interval=0.0,
                max_iterations=2,
                tail_lines=20,
                default_timeout=30,
                stop_on_failure=False,
            )

            with (
                patch(
                    "ops.continuous.continuous_runner.load_tasks",
                    side_effect=[[task], ValueError("broken schema")],
                ) as load_tasks_mock,
                patch(
                    "ops.continuous.continuous_runner.run_task",
                    return_value=self._passed_result("dynamic_task"),
                ),
                patch(
                    "ops.continuous.continuous_runner.persist_iteration",
                    return_value=repo_root / "report.json",
                ),
            ):
                exit_code = run_loop(args)

        self.assertEqual(exit_code, 1)
        self.assertEqual(load_tasks_mock.call_count, 2)

    def test_run_loop_continues_iteration_from_latest_report(self):
        task = TaskDefinition(
            name="dynamic_task",
            module="test",
            cwd=Path("."),
            command=["python", "-m", "pytest"],
            timeout=30,
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            repo_root = Path(temp_dir)
            log_dir = repo_root / "logs"
            log_dir.mkdir(parents=True, exist_ok=True)
            (log_dir / "latest.json").write_text(
                json.dumps({"iteration": 7}, ensure_ascii=False),
                encoding="utf-8",
            )
            args = Namespace(
                repo_root=repo_root,
                tasks_file=repo_root / "tasks.json",
                log_dir=log_dir,
                interval=0.0,
                max_iterations=1,
                tail_lines=20,
                default_timeout=30,
                stop_on_failure=False,
            )
            captured: list[dict[str, object]] = []
            report_path = repo_root / "report.json"

            def capture_iteration_payload(_log_dir: Path, payload: dict[str, object]) -> Path:
                captured.append(payload.copy())
                return report_path

            with (
                patch(
                    "ops.continuous.continuous_runner.load_tasks",
                    return_value=[task],
                ),
                patch(
                    "ops.continuous.continuous_runner.run_task",
                    return_value=self._passed_result("dynamic_task"),
                ),
                patch(
                    "ops.continuous.continuous_runner.persist_iteration",
                    side_effect=capture_iteration_payload,
                ),
            ):
                exit_code = run_loop(args)

        self.assertEqual(exit_code, 0)
        self.assertEqual(len(captured), 1)
        self.assertEqual(captured[0]["iteration"], 8)

    def test_run_loop_falls_back_to_iteration_one_when_latest_report_is_broken(self):
        task = TaskDefinition(
            name="dynamic_task",
            module="test",
            cwd=Path("."),
            command=["python", "-m", "pytest"],
            timeout=30,
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            repo_root = Path(temp_dir)
            log_dir = repo_root / "logs"
            log_dir.mkdir(parents=True, exist_ok=True)
            (log_dir / "latest.json").write_text("{broken-json", encoding="utf-8")
            args = Namespace(
                repo_root=repo_root,
                tasks_file=repo_root / "tasks.json",
                log_dir=log_dir,
                interval=0.0,
                max_iterations=1,
                tail_lines=20,
                default_timeout=30,
                stop_on_failure=False,
            )
            captured: list[dict[str, object]] = []
            report_path = repo_root / "report.json"

            def capture_iteration_payload(_log_dir: Path, payload: dict[str, object]) -> Path:
                captured.append(payload.copy())
                return report_path

            with (
                patch(
                    "ops.continuous.continuous_runner.load_tasks",
                    return_value=[task],
                ),
                patch(
                    "ops.continuous.continuous_runner.run_task",
                    return_value=self._passed_result("dynamic_task"),
                ),
                patch(
                    "ops.continuous.continuous_runner.persist_iteration",
                    side_effect=capture_iteration_payload,
                ),
            ):
                exit_code = run_loop(args)

        self.assertEqual(exit_code, 0)
        self.assertEqual(len(captured), 1)
        self.assertEqual(captured[0]["iteration"], 1)

    def test_run_loop_parallel_workers_execute_tasks_concurrently_and_keep_order(self):
        first_task = TaskDefinition(
            name="first_task",
            module="test",
            cwd=Path("."),
            command=["python", "-m", "pytest"],
            timeout=30,
        )
        second_task = TaskDefinition(
            name="second_task",
            module="test",
            cwd=Path("."),
            command=["python", "-m", "pytest"],
            timeout=30,
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            repo_root = Path(temp_dir)
            args = Namespace(
                repo_root=repo_root,
                tasks_file=repo_root / "tasks.json",
                log_dir=repo_root / "logs",
                interval=0.0,
                max_iterations=1,
                tail_lines=20,
                default_timeout=30,
                max_workers=2,
                stop_on_failure=False,
            )
            captured: list[dict[str, object]] = []
            report_path = repo_root / "report.json"
            lock = threading.Lock()
            running = 0
            max_running = 0

            def fake_run_task(*task_args: object, **_kwargs: object) -> dict[str, object]:
                nonlocal running, max_running
                task = task_args[0]
                assert isinstance(task, TaskDefinition)
                delay = 0.2 if task.name == "first_task" else 0.05
                with lock:
                    running += 1
                    max_running = max(max_running, running)
                time.sleep(delay)
                with lock:
                    running -= 1
                return self._passed_result(task.name)

            def capture_iteration_payload(_log_dir: Path, payload: dict[str, object]) -> Path:
                captured.append(payload.copy())
                return report_path

            with (
                patch(
                    "ops.continuous.continuous_runner.load_tasks",
                    return_value=[first_task, second_task],
                ),
                patch(
                    "ops.continuous.continuous_runner.run_task",
                    side_effect=fake_run_task,
                ),
                patch(
                    "ops.continuous.continuous_runner.persist_iteration",
                    side_effect=capture_iteration_payload,
                ),
            ):
                exit_code = run_loop(args)

        self.assertEqual(exit_code, 0)
        self.assertGreaterEqual(max_running, 2)
        self.assertEqual(len(captured), 1)
        self.assertEqual(
            [task["name"] for task in captured[0]["tasks"]],
            ["first_task", "second_task"],
        )

    def test_run_loop_forces_single_worker_for_stop_on_failure(self):
        first_task = TaskDefinition(
            name="first_task",
            module="test",
            cwd=Path("."),
            command=["python", "-m", "pytest"],
            timeout=30,
        )
        second_task = TaskDefinition(
            name="second_task",
            module="test",
            cwd=Path("."),
            command=["python", "-m", "pytest"],
            timeout=30,
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            repo_root = Path(temp_dir)
            args = Namespace(
                repo_root=repo_root,
                tasks_file=repo_root / "tasks.json",
                log_dir=repo_root / "logs",
                interval=0.0,
                max_iterations=1,
                tail_lines=20,
                default_timeout=30,
                max_workers=4,
                stop_on_failure=True,
            )
            report_path = repo_root / "report.json"
            run_count = 0

            def fake_run_task(*task_args: object, **_kwargs: object) -> dict[str, object]:
                nonlocal run_count
                run_count += 1
                task = task_args[0]
                assert isinstance(task, TaskDefinition)
                if task.name == "first_task":
                    result = self._passed_result(task.name)
                    result["status"] = "failed"
                    result["exit_code"] = 1
                    result["stderr_tail"] = "failed"
                    return result
                return self._passed_result(task.name)

            with (
                patch(
                    "ops.continuous.continuous_runner.load_tasks",
                    return_value=[first_task, second_task],
                ),
                patch(
                    "ops.continuous.continuous_runner.run_task",
                    side_effect=fake_run_task,
                ),
                patch(
                    "ops.continuous.continuous_runner.persist_iteration",
                    return_value=report_path,
                ),
                patch("sys.stderr", new_callable=io.StringIO) as stderr,
            ):
                    exit_code = run_loop(args)

        self.assertEqual(exit_code, 1)
        self.assertEqual(run_count, 1)
        self.assertIn("forcing max-workers=1", stderr.getvalue())

    def test_run_task_strips_ansi_escape_sequences(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            script = temp_path / "emit_ansi.py"
            script.write_text(
                (
                    "import sys\n"
                    "sys.stdout.write('\\x1b[31mred\\x1b[0m\\n')\n"
                    "sys.stderr.write('\\x1b[33mwarn\\x1b[0m\\n')\n"
                ),
                encoding="utf-8",
            )
            task = TaskDefinition(
                name="ansi_output",
                module="test",
                cwd=Path("."),
                command=["python", str(script.name)],
                timeout=30,
            )
            result = run_task(task, temp_path, tail_lines=20, default_timeout=30)

        self.assertEqual(result["status"], "passed")
        self.assertIn("red", result["stdout_tail"])
        self.assertIn("warn", result["stderr_tail"])
        self.assertNotIn("\u001b[", result["stdout_tail"])
        self.assertNotIn("\u001b[", result["stderr_tail"])

    def test_run_task_strips_osc_and_single_escape_sequences(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            script = temp_path / "emit_osc.py"
            script.write_text(
                (
                    "import sys\n"
                    "sys.stdout.write('\\x1b]0;runner-title\\x07ok\\n')\n"
                    "sys.stderr.write('\\x1b7saved\\x1b8\\n')\n"
                ),
                encoding="utf-8",
            )
            task = TaskDefinition(
                name="osc_output",
                module="test",
                cwd=Path("."),
                command=["python", str(script.name)],
                timeout=30,
            )
            result = run_task(task, temp_path, tail_lines=20, default_timeout=30)

        self.assertEqual(result["status"], "passed")
        self.assertEqual(result["stdout_tail"].strip(), "ok")
        self.assertEqual(result["stderr_tail"].strip(), "saved")
        self.assertNotIn("\u001b]", result["stdout_tail"])
        self.assertNotIn("\u001b7", result["stderr_tail"])


if __name__ == "__main__":
    unittest.main()
