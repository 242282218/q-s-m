from __future__ import annotations

import argparse
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen


DEFAULT_IMAGE_TAG = "qsm-local-smoke"
DEFAULT_CONTAINER_NAME = "qsm-local-smoke"
DEFAULT_HOST_PORT = 18000
DEFAULT_TIMEOUT_SECONDS = 60


@dataclass(frozen=True)
class SmokeConfig:
    repo_root: Path
    image_tag: str
    container_name: str
    host_port: int
    timeout_seconds: int
    build_image: bool
    keep_container: bool
    api_key: str
    tmdb_api_key: str
    quark_transfer_cookie: str


def build_docker_build_command(config: SmokeConfig) -> list[str]:
    return ["docker", "build", "-t", config.image_tag, "."]


def build_docker_run_command(config: SmokeConfig) -> list[str]:
    return [
        "docker",
        "run",
        "-d",
        "--rm",
        "--name",
        config.container_name,
        "-p",
        f"{config.host_port}:8000",
        "-e",
        f"API_KEY={config.api_key}",
        "-e",
        f"TMDB_API_KEY={config.tmdb_api_key}",
        "-e",
        f"QUARK_TRANSFER_COOKIE={config.quark_transfer_cookie}",
        config.image_tag,
    ]


def build_health_urls(config: SmokeConfig) -> tuple[str, str]:
    base_url = f"http://127.0.0.1:{config.host_port}/api/v1/health"
    return f"{base_url}/live", f"{base_url}/ready"


def run_command(command: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=str(cwd),
        check=True,
        capture_output=True,
        text=True,
    )


def cleanup_container(config: SmokeConfig) -> None:
    subprocess.run(
        ["docker", "rm", "-f", config.container_name],
        cwd=str(config.repo_root),
        check=False,
        capture_output=True,
        text=True,
    )


def print_logs(config: SmokeConfig) -> None:
    result = subprocess.run(
        ["docker", "logs", config.container_name],
        cwd=str(config.repo_root),
        check=False,
        capture_output=True,
        text=True,
    )
    output = result.stdout or result.stderr
    if output:
        print(output, file=sys.stderr, end="" if output.endswith("\n") else "\n")


def wait_for_url(url: str, timeout_seconds: int) -> None:
    deadline = time.time() + timeout_seconds
    last_error: Exception | None = None
    while time.time() < deadline:
        try:
            with urlopen(url, timeout=5) as response:
                status_code = getattr(response, "status", response.getcode())
                if 200 <= status_code < 300:
                    return
                last_error = RuntimeError(f"unexpected status code {status_code} for {url}")
        except Exception as exc:  # pragma: no cover - exercised via monkeypatch in tests
            last_error = exc
        time.sleep(2)
    message = f"timed out waiting for {url}"
    if last_error is not None:
        message = f"{message}: {last_error}"
    raise RuntimeError(message)


def ensure_docker_available() -> None:
    run_command(["docker", "--version"], Path.cwd())


def run_smoke(config: SmokeConfig) -> None:
    ensure_docker_available()

    if config.build_image:
        print(f"[qsm-smoke] building image {config.image_tag}")
        run_command(build_docker_build_command(config), config.repo_root)

    print(f"[qsm-smoke] starting container {config.container_name}")
    run_command(build_docker_run_command(config), config.repo_root)

    live_url, ready_url = build_health_urls(config)
    try:
        print(f"[qsm-smoke] probing {live_url}")
        wait_for_url(live_url, config.timeout_seconds)
        print(f"[qsm-smoke] probing {ready_url}")
        wait_for_url(ready_url, config.timeout_seconds)
        print("[qsm-smoke] smoke test passed")
    except Exception:
        print_logs(config)
        raise
    finally:
        if not config.keep_container:
            cleanup_container(config)


def parse_args() -> SmokeConfig:
    parser = argparse.ArgumentParser(description="Build and smoke-test the local QSM Docker image.")
    parser.add_argument(
        "--repo-root",
        default=Path(__file__).resolve().parents[2],
        type=Path,
        help="Repository root containing the Dockerfile.",
    )
    parser.add_argument("--image-tag", default=DEFAULT_IMAGE_TAG)
    parser.add_argument("--container-name", default=DEFAULT_CONTAINER_NAME)
    parser.add_argument("--host-port", type=int, default=DEFAULT_HOST_PORT)
    parser.add_argument("--timeout-seconds", type=int, default=DEFAULT_TIMEOUT_SECONDS)
    parser.add_argument("--skip-build", action="store_true", help="Reuse an existing local image tag.")
    parser.add_argument(
        "--keep-container",
        action="store_true",
        help="Keep the container running after a successful smoke test for manual inspection.",
    )
    parser.add_argument("--api-key", default="smoke-api-key")
    parser.add_argument("--tmdb-api-key", default="smoke-tmdb-key")
    parser.add_argument("--quark-transfer-cookie", default="smoke-quark-cookie")

    args = parser.parse_args()
    if args.host_port <= 0:
        raise SystemExit("--host-port must be positive")
    if args.timeout_seconds <= 0:
        raise SystemExit("--timeout-seconds must be positive")

    return SmokeConfig(
        repo_root=args.repo_root.resolve(),
        image_tag=args.image_tag,
        container_name=args.container_name,
        host_port=args.host_port,
        timeout_seconds=args.timeout_seconds,
        build_image=not args.skip_build,
        keep_container=args.keep_container,
        api_key=args.api_key,
        tmdb_api_key=args.tmdb_api_key,
        quark_transfer_cookie=args.quark_transfer_cookie,
    )


def main() -> int:
    config = parse_args()
    try:
        run_smoke(config)
    except FileNotFoundError as exc:
        print(f"[qsm-smoke] missing dependency: {exc}", file=sys.stderr)
        return 127
    except subprocess.CalledProcessError as exc:
        output = exc.stdout or exc.stderr or str(exc)
        print(f"[qsm-smoke] command failed: {output}", file=sys.stderr)
        return exc.returncode or 1
    except (RuntimeError, URLError) as exc:
        print(f"[qsm-smoke] {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
