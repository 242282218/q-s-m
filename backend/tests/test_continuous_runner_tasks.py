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
    DEFAULT_AGENT_MODEL,
    DEFAULT_AGENT_NAME,
    DEFAULT_TASKS_FILE,
    TaskDefinition,
    build_suggestions,
    load_tasks,
    reserve_next_iteration,
    run_loop,
    run_task,
)


class ContinuousRunnerTaskFileTests(unittest.TestCase):
    @staticmethod
    def _passed_result(
        name: str,
        agent: str = DEFAULT_AGENT_NAME,
        model: str = DEFAULT_AGENT_MODEL,
    ) -> dict[str, object]:
        return {
            "name": name,
            "module": "test",
            "agent": agent,
            "model": model,
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
                "frontend_lint_check",
                "frontend_format_check",
                "frontend_vitest",
                "frontend_build",
                "performance_benchmark",
            }.issubset(tasks_by_name)
        )
        frontend_lint_check = tasks_by_name["frontend_lint_check"]
        self.assertEqual(frontend_lint_check.cwd, Path("frontend"))
        self.assertEqual(frontend_lint_check.command, ["pnpm", "run", "lint:check"])
        self.assertEqual(frontend_lint_check.timeout, 900)
        self.assertEqual(frontend_lint_check.agent, "frontend-agent")
        self.assertEqual(frontend_lint_check.model, DEFAULT_AGENT_MODEL)

        frontend_format_check = tasks_by_name["frontend_format_check"]
        self.assertEqual(frontend_format_check.cwd, Path("frontend"))
        self.assertEqual(frontend_format_check.command, ["pnpm", "run", "format:check"])
        self.assertEqual(frontend_format_check.timeout, 900)
        self.assertEqual(frontend_format_check.agent, "frontend-agent")
        self.assertEqual(frontend_format_check.model, DEFAULT_AGENT_MODEL)

        frontend_build = tasks_by_name["frontend_build"]
        self.assertEqual(frontend_build.cwd, Path("frontend"))
        self.assertEqual(frontend_build.command, ["pnpm", "build"])
        self.assertEqual(frontend_build.timeout, 900)
        self.assertEqual(frontend_build.agent, "frontend-agent")
        self.assertEqual(frontend_build.model, DEFAULT_AGENT_MODEL)

        performance_task = tasks_by_name["performance_benchmark"]
        self.assertEqual(performance_task.cwd, Path("backend"))
        self.assertEqual(
            performance_task.command,
            ["python", "../tests/performance/benchmark.py", "--output-json"],
        )
        self.assertEqual(performance_task.agent, "backend-agent")
        self.assertEqual(performance_task.model, DEFAULT_AGENT_MODEL)

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

    def test_load_tasks_rejects_missing_tasks_field(self):
        payload = {"version": 1}

        with tempfile.TemporaryDirectory() as temp_dir:
            tasks_file = Path(temp_dir) / "tasks.invalid.json"
            tasks_file.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaisesRegex(
                ValueError, r"missing required 'tasks' field"
            ):
                load_tasks(tasks_file)

    def test_load_tasks_rejects_unknown_root_fields(self):
        payload = {"tasks": [], "version": 1}

        with tempfile.TemporaryDirectory() as temp_dir:
            tasks_file = Path(temp_dir) / "tasks.invalid.json"
            tasks_file.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaisesRegex(
                ValueError, r"root has unsupported fields: version"
            ):
                load_tasks(tasks_file)

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

    def test_load_tasks_rejects_non_boolean_enabled_field(self):
        payload = {
            "tasks": [
                {
                    "name": "backend_pytest",
                    "module": "backend",
                    "cwd": "backend",
                    "command": ["python", "-m", "pytest"],
                    "enabled": "true",
                }
            ]
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            tasks_file = Path(temp_dir) / "tasks.invalid.json"
            tasks_file.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaisesRegex(
                ValueError, r"tasks\[0\]\.enabled must be a boolean"
            ):
                load_tasks(tasks_file)

    def test_load_tasks_validates_disabled_task_definition(self):
        payload = {
            "tasks": [
                {
                    "name": "broken_disabled_task",
                    "module": "backend",
                    "cwd": "backend",
                    "command": "python -m pytest",
                    "enabled": False,
                }
            ]
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            tasks_file = Path(temp_dir) / "tasks.invalid-disabled.json"
            tasks_file.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaisesRegex(
                ValueError, r"tasks\[0\]: Invalid task command"
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

    def test_load_tasks_rejects_empty_task_name(self):
        payload = {
            "tasks": [
                {
                    "name": " ",
                    "module": "backend",
                    "cwd": "backend",
                    "command": ["python", "-m", "pytest"],
                }
            ]
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            tasks_file = Path(temp_dir) / "tasks.invalid.json"
            tasks_file.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaisesRegex(
                ValueError, r"tasks\[0\]: Task field 'name' must be a non-empty string"
            ):
                load_tasks(tasks_file)

    def test_load_tasks_rejects_duplicate_task_names(self):
        payload = {
            "tasks": [
                {
                    "name": "backend_pytest",
                    "module": "backend",
                    "cwd": "backend",
                    "command": ["python", "-m", "pytest"],
                },
                {
                    "name": "backend_pytest",
                    "module": "frontend",
                    "cwd": "frontend",
                    "command": ["pnpm", "test"],
                },
            ]
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            tasks_file = Path(temp_dir) / "tasks.invalid.json"
            tasks_file.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaisesRegex(
                ValueError, r"duplicate task name 'backend_pytest' at tasks\[1\]"
            ):
                load_tasks(tasks_file)

    def test_load_tasks_rejects_duplicate_task_names_with_disabled_task(self):
        payload = {
            "tasks": [
                {
                    "name": "backend_pytest",
                    "module": "backend",
                    "cwd": "backend",
                    "command": ["python", "-m", "pytest"],
                    "enabled": True,
                },
                {
                    "name": "backend_pytest",
                    "module": "backend",
                    "cwd": "backend",
                    "command": ["python", "-m", "pytest"],
                    "enabled": False,
                },
            ]
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            tasks_file = Path(temp_dir) / "tasks.duplicate-disabled.json"
            tasks_file.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaisesRegex(
                ValueError, r"duplicate task name 'backend_pytest' at tasks\[1\]"
            ):
                load_tasks(tasks_file)

    def test_load_tasks_rejects_non_positive_or_non_integer_timeout(self):
        invalid_timeouts = ["30", 0, -1, True]

        for timeout in invalid_timeouts:
            payload = {
                "tasks": [
                    {
                        "name": "backend_pytest",
                        "module": "backend",
                        "cwd": "backend",
                        "command": ["python", "-m", "pytest"],
                        "timeout": timeout,
                    }
                ]
            }

            with self.subTest(timeout=timeout):
                with tempfile.TemporaryDirectory() as temp_dir:
                    tasks_file = Path(temp_dir) / "tasks.invalid.json"
                    tasks_file.write_text(json.dumps(payload), encoding="utf-8")
                    with self.assertRaisesRegex(
                        ValueError,
                        r"Task field 'timeout' must be a positive integer",
                    ):
                        load_tasks(tasks_file)

    def test_load_tasks_rejects_non_string_or_empty_command_parts(self):
        invalid_commands = [
            ["python", 1],
            ["python", ""],
            ["python", "   "],
            [True],
        ]

        for command in invalid_commands:
            payload = {
                "tasks": [
                    {
                        "name": "backend_pytest",
                        "module": "backend",
                        "cwd": "backend",
                        "command": command,
                    }
                ]
            }

            with self.subTest(command=command):
                with tempfile.TemporaryDirectory() as temp_dir:
                    tasks_file = Path(temp_dir) / "tasks.invalid.json"
                    tasks_file.write_text(json.dumps(payload), encoding="utf-8")
                    with self.assertRaisesRegex(
                        ValueError,
                        r"Task field 'command' must be a non-empty string array",
                    ):
                        load_tasks(tasks_file)

    def test_load_tasks_rejects_unknown_task_top_level_fields(self):
        payload = {
            "tasks": [
                {
                    "name": "backend_pytest",
                    "module": "backend",
                    "cwd": "backend",
                    "command": ["python", "-m", "pytest"],
                    "timout": 60,
                }
            ]
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            tasks_file = Path(temp_dir) / "tasks.unknown-field.json"
            tasks_file.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaisesRegex(
                ValueError,
                r"tasks\[0\] has unsupported fields: timout",
            ):
                load_tasks(tasks_file)

    def test_load_tasks_defaults_agent_and_model(self):
        payload = {
            "tasks": [
                {
                    "name": "backend_pytest",
                    "module": "backend",
                    "cwd": "backend",
                    "command": ["python", "-m", "pytest"],
                }
            ]
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            tasks_file = Path(temp_dir) / "tasks.default-agent.json"
            tasks_file.write_text(json.dumps(payload), encoding="utf-8")
            tasks = load_tasks(tasks_file)

        self.assertEqual(len(tasks), 1)
        self.assertEqual(tasks[0].agent, DEFAULT_AGENT_NAME)
        self.assertEqual(tasks[0].model, DEFAULT_AGENT_MODEL)

    def test_load_tasks_rejects_non_object_agent_field(self):
        payload = {
            "tasks": [
                {
                    "name": "backend_pytest",
                    "module": "backend",
                    "cwd": "backend",
                    "command": ["python", "-m", "pytest"],
                    "agent": "backend-agent",
                }
            ]
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            tasks_file = Path(temp_dir) / "tasks.invalid-agent.json"
            tasks_file.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaisesRegex(
                ValueError,
                r"Task field 'agent' must be a JSON object",
            ):
                load_tasks(tasks_file)

    def test_load_tasks_rejects_unknown_agent_fields(self):
        payload = {
            "tasks": [
                {
                    "name": "backend_pytest",
                    "module": "backend",
                    "cwd": "backend",
                    "command": ["python", "-m", "pytest"],
                    "agent": {"name": "backend-agent", "model": "gpt-5.4", "role": "qa"},
                }
            ]
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            tasks_file = Path(temp_dir) / "tasks.invalid-agent-field.json"
            tasks_file.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaisesRegex(
                ValueError,
                r"only supports keys 'name' and 'model' \(got: role\)",
            ):
                load_tasks(tasks_file)

    def test_load_tasks_rejects_non_gpt_54_agent_model(self):
        payload = {
            "tasks": [
                {
                    "name": "backend_pytest",
                    "module": "backend",
                    "cwd": "backend",
                    "command": ["python", "-m", "pytest"],
                    "agent": {"name": "backend-agent", "model": "gpt-4.1"},
                }
            ]
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            tasks_file = Path(temp_dir) / "tasks.invalid-agent-model.json"
            tasks_file.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaisesRegex(
                ValueError,
                r"Task field 'agent.model' must be 'gpt-5.4'",
            ):
                load_tasks(tasks_file)

    def test_build_suggestions_includes_task_cwd_fix_guidance(self):
        error_texts = [
            "Task cwd '..' escapes repo root 'C:/repo'.",
            "Task cwd 'missing-dir' does not exist under repo root 'C:/repo'.",
            "Task cwd 'task.cwd' is not a directory under repo root 'C:/repo'.",
        ]

        for error_text in error_texts:
            with self.subTest(error_text=error_text):
                failed = self._passed_result("cwd_task")
                failed["status"] = "failed"
                failed["exit_code"] = 78
                failed["stderr_tail"] = error_text
                suggestions = build_suggestions([failed])
                self.assertIn(
                    "cwd_task: fix task.cwd to an existing directory under repo_root.",
                    suggestions,
                )

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

    def test_run_loop_returns_error_when_persist_iteration_fails(self):
        task = TaskDefinition(
            name="persist_failure_task",
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
                max_workers=1,
                stop_on_failure=False,
            )
            with (
                patch(
                    "ops.continuous.continuous_runner.load_tasks",
                    return_value=[task],
                ),
                patch(
                    "ops.continuous.continuous_runner.run_task",
                    return_value=self._passed_result(task.name),
                ),
                patch(
                    "ops.continuous.continuous_runner.persist_iteration",
                    side_effect=OSError("disk full"),
                ),
                patch("sys.stderr", new_callable=io.StringIO) as stderr,
            ):
                exit_code = run_loop(args)

        self.assertEqual(exit_code, 1)
        self.assertIn("Failed to persist iteration report", stderr.getvalue())
        self.assertIn("disk full", stderr.getvalue())

    def test_run_loop_returns_error_for_negative_max_iterations(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            repo_root = Path(temp_dir)
            tasks_file = repo_root / "tasks.json"
            args = Namespace(
                repo_root=repo_root,
                tasks_file=tasks_file,
                log_dir=repo_root / "logs",
                interval=1.0,
                max_iterations=-1,
                tail_lines=20,
                default_timeout=30,
                max_workers=1,
                stop_on_failure=False,
            )
            with (
                patch("ops.continuous.continuous_runner.load_tasks") as load_tasks_mock,
                patch("sys.stderr", new_callable=io.StringIO) as stderr,
            ):
                exit_code = run_loop(args)

        self.assertEqual(exit_code, 1)
        load_tasks_mock.assert_not_called()
        self.assertIn("max_iterations", stderr.getvalue())

    def test_run_loop_returns_error_for_negative_interval(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            repo_root = Path(temp_dir)
            tasks_file = repo_root / "tasks.json"
            args = Namespace(
                repo_root=repo_root,
                tasks_file=tasks_file,
                log_dir=repo_root / "logs",
                interval=-0.1,
                max_iterations=1,
                tail_lines=20,
                default_timeout=30,
                max_workers=1,
                stop_on_failure=False,
            )
            with (
                patch("ops.continuous.continuous_runner.load_tasks") as load_tasks_mock,
                patch("sys.stderr", new_callable=io.StringIO) as stderr,
            ):
                exit_code = run_loop(args)

        self.assertEqual(exit_code, 1)
        load_tasks_mock.assert_not_called()
        self.assertIn("interval", stderr.getvalue())

    def test_run_loop_returns_error_for_non_positive_tail_lines(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            repo_root = Path(temp_dir)
            tasks_file = repo_root / "tasks.json"
            args = Namespace(
                repo_root=repo_root,
                tasks_file=tasks_file,
                log_dir=repo_root / "logs",
                interval=1.0,
                max_iterations=1,
                tail_lines=0,
                default_timeout=30,
                max_workers=1,
                stop_on_failure=False,
            )
            with (
                patch("ops.continuous.continuous_runner.load_tasks") as load_tasks_mock,
                patch("sys.stderr", new_callable=io.StringIO) as stderr,
            ):
                exit_code = run_loop(args)

        self.assertEqual(exit_code, 1)
        load_tasks_mock.assert_not_called()
        self.assertIn("tail_lines", stderr.getvalue())

    def test_run_loop_returns_error_for_non_positive_default_timeout(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            repo_root = Path(temp_dir)
            tasks_file = repo_root / "tasks.json"
            args = Namespace(
                repo_root=repo_root,
                tasks_file=tasks_file,
                log_dir=repo_root / "logs",
                interval=1.0,
                max_iterations=1,
                tail_lines=20,
                default_timeout=0,
                max_workers=1,
                stop_on_failure=False,
            )
            with (
                patch("ops.continuous.continuous_runner.load_tasks") as load_tasks_mock,
                patch("sys.stderr", new_callable=io.StringIO) as stderr,
            ):
                exit_code = run_loop(args)

        self.assertEqual(exit_code, 1)
        load_tasks_mock.assert_not_called()
        self.assertIn("default_timeout", stderr.getvalue())

    def test_run_loop_returns_error_for_non_positive_max_workers(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            repo_root = Path(temp_dir)
            tasks_file = repo_root / "tasks.json"
            args = Namespace(
                repo_root=repo_root,
                tasks_file=tasks_file,
                log_dir=repo_root / "logs",
                interval=1.0,
                max_iterations=1,
                tail_lines=20,
                default_timeout=30,
                max_workers=0,
                stop_on_failure=False,
            )
            with (
                patch("ops.continuous.continuous_runner.load_tasks") as load_tasks_mock,
                patch("sys.stderr", new_callable=io.StringIO) as stderr,
            ):
                exit_code = run_loop(args)

        self.assertEqual(exit_code, 1)
        load_tasks_mock.assert_not_called()
        self.assertIn("max_workers", stderr.getvalue())

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

    def test_run_loop_max_iterations_counts_current_run_when_resuming(self):
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
                max_iterations=2,
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
                    side_effect=[[task], [task]],
                ) as load_tasks_mock,
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
        self.assertEqual(load_tasks_mock.call_count, 2)
        self.assertEqual([item["iteration"] for item in captured], [8, 9])

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

    def test_run_loop_uses_history_when_latest_report_is_broken(self):
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
            (log_dir / "iteration-0009-20260101-000000.json").write_text(
                "{}",
                encoding="utf-8",
            )
            (log_dir / "iteration-0012-20260101-000001.json").write_text(
                "{}",
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
        self.assertEqual(captured[0]["iteration"], 13)

    def test_run_loop_uses_higher_iteration_from_history_when_latest_is_stale(self):
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
            (log_dir / "iteration-0011-20260101-000001.json").write_text(
                "{}",
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
        self.assertEqual(captured[0]["iteration"], 12)

    def test_reserve_next_iteration_returns_unique_values_across_threads(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            log_dir = Path(temp_dir) / "logs"
            log_dir.mkdir(parents=True, exist_ok=True)
            (log_dir / "latest.json").write_text(
                json.dumps({"iteration": 12}, ensure_ascii=False),
                encoding="utf-8",
            )
            barrier = threading.Barrier(3)
            results: list[int] = []
            errors: list[BaseException] = []
            lock = threading.Lock()

            def reserve_in_thread() -> None:
                try:
                    barrier.wait(timeout=5)
                    iteration = reserve_next_iteration(log_dir)
                    with lock:
                        results.append(iteration)
                except BaseException as err:
                    with lock:
                        errors.append(err)

            threads = [
                threading.Thread(target=reserve_in_thread),
                threading.Thread(target=reserve_in_thread),
            ]
            for thread in threads:
                thread.start()

            barrier.wait(timeout=5)

            for thread in threads:
                thread.join(timeout=5)

            self.assertEqual(errors, [])
            self.assertEqual(sorted(results), [13, 14])
            self.assertEqual(
                (log_dir / ".iteration-counter").read_text(encoding="utf-8").strip(),
                "14",
            )

    def test_run_loop_parallel_workers_execute_tasks_concurrently_and_keep_order(self):
        first_task = TaskDefinition(
            name="first_task",
            module="test",
            cwd=Path("."),
            command=["python", "-m", "pytest"],
            timeout=30,
            agent="backend-agent",
        )
        second_task = TaskDefinition(
            name="second_task",
            module="test",
            cwd=Path("."),
            command=["python", "-m", "pytest"],
            timeout=30,
            agent="frontend-agent",
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
                return self._passed_result(task.name, task.agent, task.model)

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
        self.assertEqual(
            [task["agent"] for task in captured[0]["tasks"]],
            ["backend-agent", "frontend-agent"],
        )

    def test_run_loop_parallel_workers_keep_same_agent_tasks_sequential(self):
        first_task = TaskDefinition(
            name="first_task",
            module="test",
            cwd=Path("."),
            command=["python", "-m", "pytest"],
            timeout=30,
            agent="shared-agent",
        )
        second_task = TaskDefinition(
            name="second_task",
            module="test",
            cwd=Path("."),
            command=["python", "-m", "pytest"],
            timeout=30,
            agent="shared-agent",
        )
        third_task = TaskDefinition(
            name="third_task",
            module="test",
            cwd=Path("."),
            command=["python", "-m", "pytest"],
            timeout=30,
            agent="independent-agent",
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
                max_workers=3,
                stop_on_failure=False,
            )
            report_path = repo_root / "report.json"
            lock = threading.Lock()
            active_per_agent: dict[str, int] = {}
            max_same_agent_running = 0
            max_total_running = 0

            def fake_run_task(*task_args: object, **_kwargs: object) -> dict[str, object]:
                nonlocal max_same_agent_running, max_total_running
                task = task_args[0]
                assert isinstance(task, TaskDefinition)
                with lock:
                    active = active_per_agent.get(task.agent, 0) + 1
                    active_per_agent[task.agent] = active
                    total_running = sum(active_per_agent.values())
                    max_same_agent_running = max(max_same_agent_running, active)
                    max_total_running = max(max_total_running, total_running)
                time.sleep(0.1)
                with lock:
                    active_per_agent[task.agent] -= 1
                return self._passed_result(task.name, task.agent, task.model)

            with (
                patch(
                    "ops.continuous.continuous_runner.load_tasks",
                    return_value=[first_task, second_task, third_task],
                ),
                patch(
                    "ops.continuous.continuous_runner.run_task",
                    side_effect=fake_run_task,
                ),
                patch(
                    "ops.continuous.continuous_runner.persist_iteration",
                    return_value=report_path,
                ),
            ):
                exit_code = run_loop(args)

        self.assertEqual(exit_code, 0)
        self.assertEqual(max_same_agent_running, 1)
        self.assertGreaterEqual(max_total_running, 2)

    def test_run_loop_payload_includes_agent_summary(self):
        backend_task = TaskDefinition(
            name="backend_task",
            module="test",
            cwd=Path("."),
            command=["python", "-m", "pytest"],
            timeout=30,
            agent="backend-agent",
        )
        backend_flaky_task = TaskDefinition(
            name="backend_flaky_task",
            module="test",
            cwd=Path("."),
            command=["python", "-m", "pytest"],
            timeout=30,
            agent="backend-agent",
        )
        frontend_task = TaskDefinition(
            name="frontend_task",
            module="test",
            cwd=Path("."),
            command=["python", "-m", "pytest"],
            timeout=30,
            agent="frontend-agent",
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

            def fake_run_task(*task_args: object, **_kwargs: object) -> dict[str, object]:
                task = task_args[0]
                assert isinstance(task, TaskDefinition)
                if task.name == "backend_flaky_task":
                    result = self._passed_result(task.name, task.agent, task.model)
                    result["status"] = "failed"
                    result["exit_code"] = 1
                    result["stderr_tail"] = "FAILED"
                    return result
                return self._passed_result(task.name, task.agent, task.model)

            def capture_iteration_payload(_log_dir: Path, payload: dict[str, object]) -> Path:
                captured.append(payload.copy())
                return report_path

            with (
                patch(
                    "ops.continuous.continuous_runner.load_tasks",
                    return_value=[backend_task, backend_flaky_task, frontend_task],
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
        self.assertEqual(len(captured), 1)
        payload = captured[0]
        self.assertEqual(payload["agent_count"], 2)
        agents = payload["agents"]
        assert isinstance(agents, list)
        summary = {item["agent"]: item for item in agents if isinstance(item, dict)}
        self.assertEqual(summary["backend-agent"]["task_count"], 2)
        self.assertEqual(summary["backend-agent"]["failed_count"], 1)
        self.assertEqual(summary["frontend-agent"]["task_count"], 1)
        self.assertEqual(summary["frontend-agent"]["failed_count"], 0)

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

    def test_run_loop_stop_on_failure_marks_remaining_tasks_skipped(self):
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
                max_workers=1,
                stop_on_failure=True,
            )
            report_path = repo_root / "report.json"
            run_count = 0
            captured: list[dict[str, object]] = []

            def fake_run_task(*task_args: object, **_kwargs: object) -> dict[str, object]:
                nonlocal run_count
                run_count += 1
                task = task_args[0]
                assert isinstance(task, TaskDefinition)
                if task.name == "first_task":
                    result = self._passed_result(task.name)
                    result["status"] = "failed"
                    result["exit_code"] = 1
                    result["stderr_tail"] = "FAILED"
                    return result
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

        self.assertEqual(exit_code, 1)
        self.assertEqual(run_count, 1)
        self.assertEqual(len(captured), 1)
        self.assertEqual(captured[0]["overall_status"], "failed")
        self.assertEqual(captured[0]["failed_count"], 1)
        self.assertEqual(captured[0]["task_count"], 2)
        first_result = captured[0]["tasks"][0]
        second_result = captured[0]["tasks"][1]
        assert isinstance(first_result, dict)
        assert isinstance(second_result, dict)
        self.assertEqual(first_result["status"], "failed")
        self.assertEqual(second_result["status"], "skipped")
        self.assertEqual(second_result["exit_code"], 125)
        self.assertIn("Skipped because stop-on-failure", str(second_result["stderr_tail"]))

    def test_run_loop_parallel_lane_future_exception_turns_lane_tasks_into_failed_results(self):
        first_task = TaskDefinition(
            name="first_task",
            module="test",
            cwd=Path("."),
            command=["python", "-m", "pytest"],
            timeout=30,
            agent="broken-agent",
        )
        second_task = TaskDefinition(
            name="second_task",
            module="test",
            cwd=Path("."),
            command=["python", "-m", "pytest"],
            timeout=30,
            agent="broken-agent",
        )
        third_task = TaskDefinition(
            name="third_task",
            module="test",
            cwd=Path("."),
            command=["python", "-m", "pytest"],
            timeout=30,
            agent="healthy-agent",
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

            def fake_run_agent_lane(
                lane: list[tuple[int, TaskDefinition]],
                *_args: object,
                **_kwargs: object,
            ) -> list[tuple[int, dict[str, object]]]:
                if lane[0][1].agent == "broken-agent":
                    raise RuntimeError("lane crashed")
                return [
                    (index, self._passed_result(task.name, task.agent, task.model))
                    for index, task in lane
                ]

            def capture_iteration_payload(_log_dir: Path, payload: dict[str, object]) -> Path:
                captured.append(payload.copy())
                return report_path

            with (
                patch(
                    "ops.continuous.continuous_runner.load_tasks",
                    return_value=[first_task, second_task, third_task],
                ),
                patch(
                    "ops.continuous.continuous_runner.run_agent_lane",
                    side_effect=fake_run_agent_lane,
                ),
                patch(
                    "ops.continuous.continuous_runner.persist_iteration",
                    side_effect=capture_iteration_payload,
                ),
            ):
                exit_code = run_loop(args)

        self.assertEqual(exit_code, 0)
        self.assertEqual(len(captured), 1)
        self.assertEqual(captured[0]["overall_status"], "failed")
        self.assertEqual(captured[0]["failed_count"], 2)
        self.assertEqual(captured[0]["task_count"], 3)
        first_result = captured[0]["tasks"][0]
        second_result = captured[0]["tasks"][1]
        third_result = captured[0]["tasks"][2]
        assert isinstance(first_result, dict)
        assert isinstance(second_result, dict)
        assert isinstance(third_result, dict)
        self.assertEqual(first_result["status"], "failed")
        self.assertEqual(second_result["status"], "failed")
        self.assertEqual(third_result["status"], "passed")
        self.assertEqual(first_result["exit_code"], 70)
        self.assertEqual(second_result["exit_code"], 70)
        self.assertIn("RuntimeError: lane crashed", str(first_result["stderr_tail"]))
        self.assertIn("RuntimeError: lane crashed", str(second_result["stderr_tail"]))

    def test_run_loop_parallel_lane_future_logging_failure_is_non_blocking(self):
        first_task = TaskDefinition(
            name="first_task",
            module="test",
            cwd=Path("."),
            command=["python", "-m", "pytest"],
            timeout=30,
            agent="broken-agent",
        )
        second_task = TaskDefinition(
            name="second_task",
            module="test",
            cwd=Path("."),
            command=["python", "-m", "pytest"],
            timeout=30,
            agent="broken-agent",
        )
        third_task = TaskDefinition(
            name="third_task",
            module="test",
            cwd=Path("."),
            command=["python", "-m", "pytest"],
            timeout=30,
            agent="healthy-agent",
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

            def fake_run_agent_lane(
                lane: list[tuple[int, TaskDefinition]],
                *_args: object,
                **_kwargs: object,
            ) -> list[tuple[int, dict[str, object]]]:
                if lane[0][1].agent == "broken-agent":
                    raise RuntimeError("lane crashed")
                return [
                    (index, self._passed_result(task.name, task.agent, task.model))
                    for index, task in lane
                ]

            def fake_print_task_result(
                _iteration: int,
                task_name: str,
                _result: dict[str, object],
            ) -> None:
                if task_name == "first_task":
                    raise RuntimeError("result printer exploded")

            def capture_iteration_payload(_log_dir: Path, payload: dict[str, object]) -> Path:
                captured.append(payload.copy())
                return report_path

            with (
                patch(
                    "ops.continuous.continuous_runner.load_tasks",
                    return_value=[first_task, second_task, third_task],
                ),
                patch(
                    "ops.continuous.continuous_runner.run_agent_lane",
                    side_effect=fake_run_agent_lane,
                ),
                patch(
                    "ops.continuous.continuous_runner.print_task_result",
                    side_effect=fake_print_task_result,
                ),
                patch(
                    "ops.continuous.continuous_runner.persist_iteration",
                    side_effect=capture_iteration_payload,
                ),
            ):
                exit_code = run_loop(args)

        self.assertEqual(exit_code, 0)
        self.assertEqual(len(captured), 1)
        self.assertEqual(captured[0]["overall_status"], "failed")
        self.assertEqual(captured[0]["failed_count"], 2)
        first_result = captured[0]["tasks"][0]
        second_result = captured[0]["tasks"][1]
        third_result = captured[0]["tasks"][2]
        assert isinstance(first_result, dict)
        assert isinstance(second_result, dict)
        assert isinstance(third_result, dict)
        self.assertEqual(first_result["status"], "failed")
        self.assertEqual(second_result["status"], "failed")
        self.assertEqual(third_result["status"], "passed")

    def test_run_loop_parallel_lane_incomplete_results_backfills_missing_tasks(self):
        first_task = TaskDefinition(
            name="first_task",
            module="test",
            cwd=Path("."),
            command=["python", "-m", "pytest"],
            timeout=30,
            agent="broken-agent",
        )
        second_task = TaskDefinition(
            name="second_task",
            module="test",
            cwd=Path("."),
            command=["python", "-m", "pytest"],
            timeout=30,
            agent="broken-agent",
        )
        third_task = TaskDefinition(
            name="third_task",
            module="test",
            cwd=Path("."),
            command=["python", "-m", "pytest"],
            timeout=30,
            agent="healthy-agent",
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

            def fake_run_agent_lane(
                lane: list[tuple[int, TaskDefinition]],
                *_args: object,
                **_kwargs: object,
            ) -> list[tuple[int, dict[str, object]]]:
                if lane[0][1].agent == "broken-agent":
                    index, task = lane[0]
                    return [(index, self._passed_result(task.name, task.agent, task.model))]
                return [
                    (index, self._passed_result(task.name, task.agent, task.model))
                    for index, task in lane
                ]

            def capture_iteration_payload(_log_dir: Path, payload: dict[str, object]) -> Path:
                captured.append(payload.copy())
                return report_path

            with (
                patch(
                    "ops.continuous.continuous_runner.load_tasks",
                    return_value=[first_task, second_task, third_task],
                ),
                patch(
                    "ops.continuous.continuous_runner.run_agent_lane",
                    side_effect=fake_run_agent_lane,
                ),
                patch(
                    "ops.continuous.continuous_runner.persist_iteration",
                    side_effect=capture_iteration_payload,
                ),
            ):
                exit_code = run_loop(args)

        self.assertEqual(exit_code, 0)
        self.assertEqual(len(captured), 1)
        self.assertEqual(captured[0]["overall_status"], "failed")
        self.assertEqual(captured[0]["failed_count"], 1)
        self.assertEqual(captured[0]["task_count"], 3)
        first_result = captured[0]["tasks"][0]
        second_result = captured[0]["tasks"][1]
        third_result = captured[0]["tasks"][2]
        assert isinstance(first_result, dict)
        assert isinstance(second_result, dict)
        assert isinstance(third_result, dict)
        self.assertEqual(first_result["status"], "passed")
        self.assertEqual(second_result["status"], "failed")
        self.assertEqual(second_result["exit_code"], 70)
        self.assertEqual(third_result["status"], "passed")
        self.assertIn("lane returned incomplete results", str(second_result["stderr_tail"]))

    def test_run_loop_parallel_lane_unexpected_result_index_backfills_lane(self):
        first_task = TaskDefinition(
            name="first_task",
            module="test",
            cwd=Path("."),
            command=["python", "-m", "pytest"],
            timeout=30,
            agent="broken-agent",
        )
        second_task = TaskDefinition(
            name="second_task",
            module="test",
            cwd=Path("."),
            command=["python", "-m", "pytest"],
            timeout=30,
            agent="broken-agent",
        )
        third_task = TaskDefinition(
            name="third_task",
            module="test",
            cwd=Path("."),
            command=["python", "-m", "pytest"],
            timeout=30,
            agent="healthy-agent",
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

            def fake_run_agent_lane(
                lane: list[tuple[int, TaskDefinition]],
                *_args: object,
                **_kwargs: object,
            ) -> list[tuple[int, dict[str, object]]]:
                if lane[0][1].agent == "broken-agent":
                    return [(2, self._passed_result("ghost_task", "broken-agent", DEFAULT_AGENT_MODEL))]
                return [
                    (index, self._passed_result(task.name, task.agent, task.model))
                    for index, task in lane
                ]

            def capture_iteration_payload(_log_dir: Path, payload: dict[str, object]) -> Path:
                captured.append(payload.copy())
                return report_path

            with (
                patch(
                    "ops.continuous.continuous_runner.load_tasks",
                    return_value=[first_task, second_task, third_task],
                ),
                patch(
                    "ops.continuous.continuous_runner.run_agent_lane",
                    side_effect=fake_run_agent_lane,
                ),
                patch(
                    "ops.continuous.continuous_runner.persist_iteration",
                    side_effect=capture_iteration_payload,
                ),
            ):
                exit_code = run_loop(args)

        self.assertEqual(exit_code, 0)
        self.assertEqual(len(captured), 1)
        self.assertEqual(captured[0]["overall_status"], "failed")
        self.assertEqual(captured[0]["failed_count"], 2)
        self.assertEqual(captured[0]["task_count"], 3)
        first_result = captured[0]["tasks"][0]
        second_result = captured[0]["tasks"][1]
        third_result = captured[0]["tasks"][2]
        assert isinstance(first_result, dict)
        assert isinstance(second_result, dict)
        assert isinstance(third_result, dict)
        self.assertEqual(first_result["status"], "failed")
        self.assertEqual(second_result["status"], "failed")
        self.assertEqual(third_result["status"], "passed")
        self.assertIn(
            "ValueError: Agent lane returned unexpected task index 2",
            str(first_result["stderr_tail"]),
        )

    def test_run_loop_parallel_lane_runtime_exception_keeps_completed_results(self):
        first_task = TaskDefinition(
            name="first_task",
            module="test",
            cwd=Path("."),
            command=["python", "-m", "pytest"],
            timeout=30,
            agent="broken-agent",
        )
        second_task = TaskDefinition(
            name="second_task",
            module="test",
            cwd=Path("."),
            command=["python", "-m", "pytest"],
            timeout=30,
            agent="broken-agent",
        )
        third_task = TaskDefinition(
            name="third_task",
            module="test",
            cwd=Path("."),
            command=["python", "-m", "pytest"],
            timeout=30,
            agent="broken-agent",
        )
        fourth_task = TaskDefinition(
            name="fourth_task",
            module="test",
            cwd=Path("."),
            command=["python", "-m", "pytest"],
            timeout=30,
            agent="healthy-agent",
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
            run_calls: list[str] = []

            def fake_run_task_safe(
                task: TaskDefinition,
                *_args: object,
                **_kwargs: object,
            ) -> dict[str, object]:
                run_calls.append(task.name)
                if task.name == "second_task":
                    raise RuntimeError("lane exploded")
                return self._passed_result(task.name, task.agent, task.model)

            def capture_iteration_payload(_log_dir: Path, payload: dict[str, object]) -> Path:
                captured.append(payload.copy())
                return report_path

            with (
                patch(
                    "ops.continuous.continuous_runner.load_tasks",
                    return_value=[first_task, second_task, third_task, fourth_task],
                ),
                patch(
                    "ops.continuous.continuous_runner.run_task_safe",
                    side_effect=fake_run_task_safe,
                ),
                patch(
                    "ops.continuous.continuous_runner.persist_iteration",
                    side_effect=capture_iteration_payload,
                ),
            ):
                exit_code = run_loop(args)

        self.assertEqual(exit_code, 0)
        self.assertEqual(len(captured), 1)
        self.assertEqual(captured[0]["overall_status"], "failed")
        self.assertEqual(captured[0]["failed_count"], 2)
        self.assertNotIn("third_task", run_calls)
        first_result = captured[0]["tasks"][0]
        second_result = captured[0]["tasks"][1]
        third_result = captured[0]["tasks"][2]
        fourth_result = captured[0]["tasks"][3]
        assert isinstance(first_result, dict)
        assert isinstance(second_result, dict)
        assert isinstance(third_result, dict)
        assert isinstance(fourth_result, dict)
        self.assertEqual(first_result["status"], "passed")
        self.assertEqual(second_result["status"], "failed")
        self.assertEqual(third_result["status"], "failed")
        self.assertEqual(fourth_result["status"], "passed")
        self.assertIn("RuntimeError: lane exploded", str(second_result["stderr_tail"]))
        self.assertIn("RuntimeError: lane exploded", str(third_result["stderr_tail"]))

    def test_run_loop_parallel_lane_logging_failure_is_non_blocking(self):
        first_task = TaskDefinition(
            name="first_task",
            module="test",
            cwd=Path("."),
            command=["python", "-m", "pytest"],
            timeout=30,
            agent="broken-agent",
        )
        second_task = TaskDefinition(
            name="second_task",
            module="test",
            cwd=Path("."),
            command=["python", "-m", "pytest"],
            timeout=30,
            agent="broken-agent",
        )
        third_task = TaskDefinition(
            name="third_task",
            module="test",
            cwd=Path("."),
            command=["python", "-m", "pytest"],
            timeout=30,
            agent="broken-agent",
        )
        fourth_task = TaskDefinition(
            name="fourth_task",
            module="test",
            cwd=Path("."),
            command=["python", "-m", "pytest"],
            timeout=30,
            agent="healthy-agent",
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
            run_calls: list[str] = []

            def fake_run_task_safe(
                task: TaskDefinition,
                *_args: object,
                **_kwargs: object,
            ) -> dict[str, object]:
                run_calls.append(task.name)
                return self._passed_result(task.name, task.agent, task.model)

            def fake_print_task_result(
                _iteration: int,
                task_name: str,
                _result: dict[str, object],
            ) -> None:
                if task_name == "second_task":
                    raise RuntimeError("result printer exploded")

            def capture_iteration_payload(_log_dir: Path, payload: dict[str, object]) -> Path:
                captured.append(payload.copy())
                return report_path

            with (
                patch(
                    "ops.continuous.continuous_runner.load_tasks",
                    return_value=[first_task, second_task, third_task, fourth_task],
                ),
                patch(
                    "ops.continuous.continuous_runner.run_task_safe",
                    side_effect=fake_run_task_safe,
                ),
                patch(
                    "ops.continuous.continuous_runner.print_task_result",
                    side_effect=fake_print_task_result,
                ),
                patch(
                    "ops.continuous.continuous_runner.persist_iteration",
                    side_effect=capture_iteration_payload,
                ),
            ):
                exit_code = run_loop(args)

        self.assertEqual(exit_code, 0)
        self.assertEqual(len(captured), 1)
        self.assertEqual(captured[0]["overall_status"], "passed")
        self.assertEqual(captured[0]["failed_count"], 0)
        self.assertIn("third_task", run_calls)
        first_result = captured[0]["tasks"][0]
        second_result = captured[0]["tasks"][1]
        third_result = captured[0]["tasks"][2]
        fourth_result = captured[0]["tasks"][3]
        assert isinstance(first_result, dict)
        assert isinstance(second_result, dict)
        assert isinstance(third_result, dict)
        assert isinstance(fourth_result, dict)
        self.assertEqual(first_result["status"], "passed")
        self.assertEqual(second_result["status"], "passed")
        self.assertEqual(third_result["status"], "passed")
        self.assertEqual(fourth_result["status"], "passed")

    def test_run_loop_parallel_worker_exception_turns_into_failed_task(self):
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

            def fake_run_task(*task_args: object, **_kwargs: object) -> dict[str, object]:
                task = task_args[0]
                assert isinstance(task, TaskDefinition)
                if task.name == "first_task":
                    raise RuntimeError("boom")
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
        self.assertEqual(len(captured), 1)
        self.assertEqual(captured[0]["overall_status"], "failed")
        first_result = captured[0]["tasks"][0]
        second_result = captured[0]["tasks"][1]
        assert isinstance(first_result, dict)
        assert isinstance(second_result, dict)
        self.assertEqual(first_result["status"], "failed")
        self.assertEqual(first_result["exit_code"], 70)
        self.assertIn("RuntimeError: boom", str(first_result["stderr_tail"]))
        self.assertEqual(second_result["status"], "passed")

    def test_run_loop_sequential_logging_failure_is_non_blocking(self):
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
                max_workers=1,
                stop_on_failure=False,
            )
            captured: list[dict[str, object]] = []
            report_path = repo_root / "report.json"

            def fake_run_task(*task_args: object, **_kwargs: object) -> dict[str, object]:
                task = task_args[0]
                assert isinstance(task, TaskDefinition)
                return self._passed_result(task.name)

            def fake_print_task_result(
                _iteration: int,
                task_name: str,
                _result: dict[str, object],
            ) -> None:
                if task_name == "first_task":
                    raise RuntimeError("result printer exploded")

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
                    "ops.continuous.continuous_runner.print_task_result",
                    side_effect=fake_print_task_result,
                ),
                patch(
                    "ops.continuous.continuous_runner.persist_iteration",
                    side_effect=capture_iteration_payload,
                ),
            ):
                exit_code = run_loop(args)

        self.assertEqual(exit_code, 0)
        self.assertEqual(len(captured), 1)
        self.assertEqual(captured[0]["overall_status"], "passed")
        self.assertEqual(captured[0]["failed_count"], 0)
        first_result = captured[0]["tasks"][0]
        second_result = captured[0]["tasks"][1]
        assert isinstance(first_result, dict)
        assert isinstance(second_result, dict)
        self.assertEqual(first_result["status"], "passed")
        self.assertEqual(second_result["status"], "passed")

    def test_run_loop_sequential_exception_turns_into_failed_task(self):
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
                max_workers=1,
                stop_on_failure=False,
            )
            captured: list[dict[str, object]] = []
            report_path = repo_root / "report.json"

            def fake_run_task(*task_args: object, **_kwargs: object) -> dict[str, object]:
                task = task_args[0]
                assert isinstance(task, TaskDefinition)
                if task.name == "first_task":
                    raise RuntimeError("boom")
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
        self.assertEqual(len(captured), 1)
        self.assertEqual(captured[0]["overall_status"], "failed")
        first_result = captured[0]["tasks"][0]
        second_result = captured[0]["tasks"][1]
        assert isinstance(first_result, dict)
        assert isinstance(second_result, dict)
        self.assertEqual(first_result["status"], "failed")
        self.assertEqual(first_result["exit_code"], 70)
        self.assertIn("RuntimeError: boom", str(first_result["stderr_tail"]))
        self.assertEqual(second_result["status"], "passed")

    def test_run_task_rejects_parent_path_escape_cwd(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            repo_root = temp_path / "workspace"
            repo_root.mkdir()
            task = TaskDefinition(
                name="cwd_escape_parent",
                module="test",
                cwd=Path(".."),
                command=["python", "-c", "print('ok')"],
                timeout=30,
            )
            result = run_task(task, repo_root, tail_lines=20, default_timeout=30)

        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["exit_code"], 78)
        self.assertIn("escapes repo root", str(result["stderr_tail"]))

    def test_run_task_rejects_absolute_cwd_outside_repo_root(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            repo_root = temp_path / "workspace"
            outside_cwd = temp_path / "outside"
            repo_root.mkdir()
            outside_cwd.mkdir()
            task = TaskDefinition(
                name="cwd_escape_absolute",
                module="test",
                cwd=outside_cwd,
                command=["python", "-c", "print('ok')"],
                timeout=30,
            )
            result = run_task(task, repo_root, tail_lines=20, default_timeout=30)

        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["exit_code"], 78)
        self.assertIn("escapes repo root", str(result["stderr_tail"]))

    def test_run_task_rejects_symlink_cwd_escape_outside_repo_root(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            repo_root = temp_path / "workspace"
            outside_cwd = temp_path / "outside"
            repo_root.mkdir()
            outside_cwd.mkdir()
            escape_link = repo_root / "escape-link"
            try:
                escape_link.symlink_to(outside_cwd, target_is_directory=True)
            except (OSError, NotImplementedError) as err:
                self.skipTest(f"symlink unavailable in test environment: {err}")
            task = TaskDefinition(
                name="cwd_escape_symlink",
                module="test",
                cwd=Path("escape-link"),
                command=["python", "-c", "print('ok')"],
                timeout=30,
            )
            result = run_task(task, repo_root, tail_lines=20, default_timeout=30)

        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["exit_code"], 78)
        self.assertIn("escapes repo root", str(result["stderr_tail"]))

    def test_run_task_rejects_missing_cwd_inside_repo_root(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            repo_root = temp_path / "workspace"
            repo_root.mkdir()
            task = TaskDefinition(
                name="cwd_missing",
                module="test",
                cwd=Path("missing-dir"),
                command=["python", "-c", "print('ok')"],
                timeout=30,
            )
            result = run_task(task, repo_root, tail_lines=20, default_timeout=30)

        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["exit_code"], 78)
        self.assertIn("does not exist", str(result["stderr_tail"]))

    def test_run_task_rejects_non_directory_cwd_inside_repo_root(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            repo_root = temp_path / "workspace"
            repo_root.mkdir()
            not_directory = repo_root / "task.cwd"
            not_directory.write_text("not a dir", encoding="utf-8")
            task = TaskDefinition(
                name="cwd_not_directory",
                module="test",
                cwd=Path("task.cwd"),
                command=["python", "-c", "print('ok')"],
                timeout=30,
            )
            result = run_task(task, repo_root, tail_lines=20, default_timeout=30)

        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["exit_code"], 78)
        self.assertIn("not a directory", str(result["stderr_tail"]))

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
        self.assertEqual(result["agent"], DEFAULT_AGENT_NAME)
        self.assertEqual(result["model"], DEFAULT_AGENT_MODEL)
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
