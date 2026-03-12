import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


class DeploymentConfigTests(unittest.TestCase):
    def setUp(self) -> None:
        self.compose_content = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
        self.dockerfile_content = (ROOT / "Dockerfile").read_text(encoding="utf-8")

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


if __name__ == "__main__":
    unittest.main()
