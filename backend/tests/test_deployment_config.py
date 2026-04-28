import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


class DeploymentConfigTests(unittest.TestCase):
    def setUp(self) -> None:
        self.compose_content = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
        self.dockerfile_content = (ROOT / "Dockerfile").read_text(encoding="utf-8")
        self.env_example_content = (ROOT / ".env.example").read_text(encoding="utf-8")
        self.quality_gates_content = (
            ROOT / ".github" / "workflows" / "quality-gates.yml"
        ).read_text(encoding="utf-8")
        self.docker_ghcr_main_content = (
            ROOT / ".github" / "workflows" / "docker-ghcr-main.yml"
        ).read_text(encoding="utf-8")
        self.release_docker_content = (
            ROOT / ".github" / "workflows" / "release-docker.yml"
        ).read_text(encoding="utf-8")
        self.readme_content = (ROOT / "README.md").read_text(encoding="utf-8")
        self.test_guide_content = (ROOT / "backend" / "tests" / "TEST_GUIDE.md").read_text(encoding="utf-8")
        self.dev_requirements_content = (
            ROOT / "backend" / "requirements-dev.lock.txt"
        ).read_text(encoding="utf-8")
        self.docker_with_nginx_doc = (
            ROOT / "docs" / "deployment" / "docker-with-nginx.md"
        ).read_text(encoding="utf-8")
        self.continuous_testing_doc = (
            ROOT / "docs" / "continuous-testing-loop.md"
        ).read_text(encoding="utf-8")

    def test_compose_uses_env_file_instead_of_bind_mounting_dotenv(self):
        self.assertIn("env_file:", self.compose_content)
        self.assertIn("- .env", self.compose_content)
        self.assertNotIn("./.env:/app/.env", self.compose_content)

    def test_compose_persists_runtime_data_and_logs(self):
        self.assertIn("- ./storage/db:/app/storage/db", self.compose_content)
        self.assertIn("- ./storage/logs:/app/storage/logs", self.compose_content)
        self.assertIn("- ./storage/config:/app/storage/config", self.compose_content)

    def test_frontend_builder_accepts_vite_api_key_build_arg(self):
        self.assertIn("ARG VITE_API_KEY", self.dockerfile_content)
        self.assertIn("ENV VITE_API_KEY=$VITE_API_KEY", self.dockerfile_content)

    def test_dockerfile_healthcheck_uses_readiness_probe(self):
        self.assertIn("/api/v1/health/ready", self.dockerfile_content)
        self.assertNotIn(
            "urlopen('http://localhost:8000/api/v1/health')",
            self.dockerfile_content,
        )

    def test_dockerfile_defaults_to_single_worker_until_redis_is_enabled(self):
        self.assertIn('"--workers", "1"', self.dockerfile_content)
        self.assertIn("For multi-worker deployment, set `CACHE_TYPE=redis`", self.readme_content)

    def test_quality_gates_include_docker_build_validation(self):
        self.assertIn("name: Docker image build", self.quality_gates_content)
        self.assertIn("docker/setup-buildx-action@v3", self.quality_gates_content)
        self.assertIn("docker/build-push-action@v6", self.quality_gates_content)
        self.assertIn("platforms: linux/amd64", self.quality_gates_content)
        self.assertIn("push: false", self.quality_gates_content)
        self.assertIn("load: true", self.quality_gates_content)
        self.assertIn("Run container smoke test", self.quality_gates_content)
        self.assertIn("/api/v1/health/live", self.quality_gates_content)
        self.assertIn("/api/v1/health/ready", self.quality_gates_content)

    def test_backend_quality_gate_uses_dev_lock_file(self):
        self.assertIn("backend/requirements-dev.lock.txt", self.quality_gates_content)
        self.assertIn("-r requirements.lock.txt", self.dev_requirements_content)
        self.assertIn("pytest==", self.dev_requirements_content)
        self.assertIn("pytest-asyncio==", self.dev_requirements_content)
        self.assertIn("pytest-cov==", self.dev_requirements_content)

    def test_ghcr_workflows_publish_multi_arch_images(self):
        self.assertIn("docker/setup-qemu-action@v3", self.docker_ghcr_main_content)
        self.assertIn("platforms: linux/amd64,linux/arm64", self.docker_ghcr_main_content)
        self.assertIn("GHCR_PLATFORMS: linux/amd64,linux/arm64", self.release_docker_content)
        self.assertIn("docker/setup-qemu-action@v3", self.release_docker_content)
        self.assertIn(
            "Build and push multi-arch image",
            self.release_docker_content,
        )

    def test_env_example_uses_safe_cors_default_when_debug_disabled(self):
        self.assertIn("DEBUG=false", self.env_example_content)
        cors_line = next(
            line
            for line in self.env_example_content.splitlines()
            if line.startswith("CORS_ORIGINS=")
        )

        self.assertNotIn("localhost", cors_line.lower())
        self.assertNotIn("127.0.0.1", cors_line)
        self.assertNotIn("::1", cors_line)
        self.assertNotIn('"*"', cors_line)

    def test_deployment_doc_distinguishes_readiness_and_detailed_health(self):
        self.assertIn("/api/v1/health/ready", self.docker_with_nginx_doc)
        self.assertIn("/api/v1/health/live", self.docker_with_nginx_doc)
        self.assertIn("/api/v1/health", self.docker_with_nginx_doc)

    def test_deployment_doc_mentions_multi_arch_ghcr_images(self):
        self.assertIn("linux/amd64", self.docker_with_nginx_doc)
        self.assertIn("linux/arm64", self.docker_with_nginx_doc)

    def test_repo_docs_document_docker_build_gate(self):
        self.assertIn("Docker image build", self.readme_content)
        self.assertIn("quality-gates.yml", self.readme_content)
        self.assertIn("health/live", self.readme_content)
        self.assertIn("health/ready", self.readme_content)

    def test_docs_reference_local_docker_smoke_script(self):
        self.assertIn("python ops/deploy/docker_smoke.py", self.readme_content)
        self.assertIn("python ops/deploy/docker_smoke.py", self.docker_with_nginx_doc)

    def test_backend_test_docs_reference_dev_lock_file(self):
        self.assertIn("requirements-dev.lock.txt", self.test_guide_content)
        self.assertIn("requirements-dev.lock.txt", self.continuous_testing_doc)

    def test_readme_documents_multi_arch_ghcr_images(self):
        self.assertIn("linux/amd64", self.readme_content)
        self.assertIn("linux/arm64", self.readme_content)
        self.assertIn("ghcr.io", self.readme_content)


if __name__ == "__main__":
    unittest.main()
