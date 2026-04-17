import importlib.util
from pathlib import Path


TARGET = Path(__file__).with_name("test_performance_benchmark.py")


def load_module():
    spec = importlib.util.spec_from_file_location("qsm_backend_performance_benchmark", TARGET)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_heavy_performance_suite_is_opt_in_marked():
    module = load_module()
    raw_marks = module.pytestmark
    marks = raw_marks if isinstance(raw_marks, list) else [raw_marks]

    assert any(getattr(mark, "name", None) == "performance" for mark in marks)
