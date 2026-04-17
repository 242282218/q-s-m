import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


class DeploymentConfigTests(unittest.TestCase):
    def setUp(self) -> None:
        self.compose_content = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
        self.dockerfile_content = (ROOT / "Dockerfile").read_text(encoding="utf-8")
        self.env_example_content = (ROOT / ".env.example").read_text(encoding="utf-8")
        self.docker_with_nginx_doc = (
            ROOT / "docs" / "deployment" / "docker-with-nginx.md"
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


if __name__ == "__main__":
    unittest.main()
