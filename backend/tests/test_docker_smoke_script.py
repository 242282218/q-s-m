from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
TARGET = ROOT / "ops" / "deploy" / "docker_smoke.py"


def load_module():
    spec = importlib.util.spec_from_file_location("qsm_docker_smoke", TARGET)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_parse_args_builds_default_smoke_config(monkeypatch: pytest.MonkeyPatch):
    module = load_module()
    monkeypatch.setattr(sys, "argv", ["docker_smoke.py"])

    config = module.parse_args()

    assert config.repo_root == ROOT
    assert config.image_tag == module.DEFAULT_IMAGE_TAG
    assert config.container_name == module.DEFAULT_CONTAINER_NAME
    assert config.host_port == module.DEFAULT_HOST_PORT
    assert config.timeout_seconds == module.DEFAULT_TIMEOUT_SECONDS
    assert config.build_image is True
    assert config.keep_container is False


def test_build_commands_use_expected_defaults():
    module = load_module()
    config = module.SmokeConfig(
        repo_root=ROOT,
        image_tag="qsm-test",
        container_name="qsm-container",
        host_port=18001,
        timeout_seconds=45,
        build_image=True,
        keep_container=False,
        api_key="a",
        tmdb_api_key="b",
        quark_transfer_cookie="c",
    )

    assert module.build_docker_build_command(config) == ["docker", "build", "-t", "qsm-test", "."]
    assert module.build_docker_run_command(config) == [
        "docker",
        "run",
        "-d",
        "--rm",
        "--name",
        "qsm-container",
        "-p",
        "18001:8000",
        "-e",
        "API_KEY=a",
        "-e",
        "TMDB_API_KEY=b",
        "-e",
        "QUARK_TRANSFER_COOKIE=c",
        "qsm-test",
    ]
    assert module.build_health_urls(config) == (
        "http://127.0.0.1:18001/api/v1/health/live",
        "http://127.0.0.1:18001/api/v1/health/ready",
    )


def test_run_smoke_cleans_up_container_after_success(monkeypatch: pytest.MonkeyPatch):
    module = load_module()
    config = module.SmokeConfig(
        repo_root=ROOT,
        image_tag="qsm-test",
        container_name="qsm-container",
        host_port=18001,
        timeout_seconds=45,
        build_image=True,
        keep_container=False,
        api_key="a",
        tmdb_api_key="b",
        quark_transfer_cookie="c",
    )
    executed_commands: list[list[str]] = []
    waited_urls: list[str] = []
    cleaned: list[str] = []

    def fake_run_command(command: list[str], cwd: Path):
        assert cwd == ROOT
        executed_commands.append(command)
        return object()

    def fake_wait_for_url(url: str, timeout_seconds: int):
        assert timeout_seconds == 45
        waited_urls.append(url)

    def fake_cleanup(target_config):
        cleaned.append(target_config.container_name)

    monkeypatch.setattr(module, "run_command", fake_run_command)
    monkeypatch.setattr(module, "wait_for_url", fake_wait_for_url)
    monkeypatch.setattr(module, "cleanup_container", fake_cleanup)

    module.run_smoke(config)

    assert executed_commands == [
        ["docker", "build", "-t", "qsm-test", "."],
        [
            "docker",
            "run",
            "-d",
            "--rm",
            "--name",
            "qsm-container",
            "-p",
            "18001:8000",
            "-e",
            "API_KEY=a",
            "-e",
            "TMDB_API_KEY=b",
            "-e",
            "QUARK_TRANSFER_COOKIE=c",
            "qsm-test",
        ],
    ]
    assert waited_urls == [
        "http://127.0.0.1:18001/api/v1/health/live",
        "http://127.0.0.1:18001/api/v1/health/ready",
    ]
    assert cleaned == ["qsm-container"]


def test_run_smoke_prints_logs_and_cleans_up_after_probe_failure(monkeypatch: pytest.MonkeyPatch):
    module = load_module()
    config = module.SmokeConfig(
        repo_root=ROOT,
        image_tag="qsm-test",
        container_name="qsm-container",
        host_port=18001,
        timeout_seconds=45,
        build_image=False,
        keep_container=False,
        api_key="a",
        tmdb_api_key="b",
        quark_transfer_cookie="c",
    )
    logs_requested: list[str] = []
    cleaned: list[str] = []

    monkeypatch.setattr(module, "run_command", lambda command, cwd: object())
    monkeypatch.setattr(
        module,
        "wait_for_url",
        lambda url, timeout_seconds: (_ for _ in ()).throw(RuntimeError("probe failed")),
    )
    monkeypatch.setattr(module, "print_logs", lambda target_config: logs_requested.append(target_config.container_name))
    monkeypatch.setattr(module, "cleanup_container", lambda target_config: cleaned.append(target_config.container_name))

    with pytest.raises(RuntimeError, match="probe failed"):
        module.run_smoke(config)

    assert logs_requested == ["qsm-container"]
    assert cleaned == ["qsm-container"]
