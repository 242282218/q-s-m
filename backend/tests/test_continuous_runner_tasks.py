import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ops.continuous.continuous_runner import (
    DEFAULT_TASKS_FILE,
    TaskDefinition,
    load_tasks,
    run_task,
)


class ContinuousRunnerTaskFileTests(unittest.TestCase):
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
