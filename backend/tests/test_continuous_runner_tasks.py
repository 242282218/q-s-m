import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ops.continuous.continuous_runner import load_tasks


class ContinuousRunnerTaskFileTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
