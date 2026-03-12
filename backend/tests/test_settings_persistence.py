import asyncio
import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.api.endpoints.settings import get_current_settings, update_env_file
from app.api.endpoints.settings import SettingsUpdate, update_settings
from app.core.config import get_settings


class SettingsPersistenceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.runtime_env_path = Path(self.temp_dir.name) / "runtime.env"
        self.original_values = {
            "QSM_RUNTIME_ENV_FILE": os.environ.get("QSM_RUNTIME_ENV_FILE"),
            "API_KEY": os.environ.get("API_KEY"),
            "TMDB_API_KEY": os.environ.get("TMDB_API_KEY"),
            "QUARK_TRANSFER_COOKIE": os.environ.get("QUARK_TRANSFER_COOKIE"),
            "LOG_LEVEL": os.environ.get("LOG_LEVEL"),
        }
        os.environ["QSM_RUNTIME_ENV_FILE"] = str(self.runtime_env_path)
        os.environ["API_KEY"] = "env-api-key-12345"
        os.environ["TMDB_API_KEY"] = "env-tmdb-api-key-12345"
        os.environ["QUARK_TRANSFER_COOKIE"] = "env-cookie=original"
        os.environ["LOG_LEVEL"] = "INFO"
        get_settings.cache_clear()

    def tearDown(self) -> None:
        get_settings.cache_clear()
        self.temp_dir.cleanup()
        for key, value in self.original_values.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    def test_update_env_file_writes_to_runtime_settings_file(self):
        update_env_file(
            {
                "API_KEY": "saved-api-key-67890",
                "TMDB_API_KEY": "saved-tmdb-api-key-67890",
                "QUARK_TRANSFER_COOKIE": "saved-cookie=updated",
                "LOG_LEVEL": "DEBUG",
            }
        )

        self.assertTrue(self.runtime_env_path.exists())
        content = self.runtime_env_path.read_text(encoding="utf-8")
        self.assertIn("API_KEY=saved-api-key-67890", content)
        self.assertIn("TMDB_API_KEY=saved-tmdb-api-key-67890", content)
        self.assertIn("QUARK_TRANSFER_COOKIE=saved-cookie=updated", content)
        self.assertIn("LOG_LEVEL=DEBUG", content)

    def test_update_settings_accepts_api_key_payload(self):
        response = asyncio.run(
            update_settings(SettingsUpdate.model_validate({"API_KEY": "saved-api-key-67890"}))
        )

        self.assertEqual(response.data.updated_keys, ["API_KEY"])
        content = self.runtime_env_path.read_text(encoding="utf-8")
        self.assertIn("API_KEY=saved-api-key-67890", content)

    def test_runtime_settings_file_overrides_process_environment(self):
        self.runtime_env_path.write_text(
            "\n".join(
                [
                    "API_KEY=file-api-key-67890",
                    "TMDB_API_KEY=file-tmdb-api-key-67890",
                    "QUARK_TRANSFER_COOKIE=file-cookie=override",
                    "LOG_LEVEL=DEBUG",
                    "",
                ]
            ),
            encoding="utf-8",
        )

        get_settings.cache_clear()
        settings = get_settings()

        self.assertEqual(settings.api_key, "file-api-key-67890")
        self.assertEqual(settings.tmdb_api_key, "file-tmdb-api-key-67890")
        self.assertEqual(settings.quark_transfer_cookie, "file-cookie=override")
        self.assertEqual(settings.log_level, "DEBUG")

    def test_get_current_settings_uses_runtime_snapshot_and_masks_secrets(self):
        self.runtime_env_path.write_text(
            "\n".join(
                [
                    "API_KEY=file-api-key-67890",
                    "TMDB_API_KEY=file-tmdb-api-key-67890",
                    "QUARK_TRANSFER_COOKIE=file-cookie=override",
                    "LOG_LEVEL=DEBUG",
                    "TRANSFER_KEEP_EXTRAS=true",
                    "",
                ]
            ),
            encoding="utf-8",
        )

        get_settings.cache_clear()
        response = asyncio.run(get_current_settings())

        self.assertEqual(response.data.LOG_LEVEL, "DEBUG")
        self.assertTrue(response.data.TRANSFER_KEEP_EXTRAS)
        self.assertTrue(response.data.API_KEY_CONFIGURED)
        self.assertEqual(response.data.API_KEY_MASKED, "fil***890")
        self.assertTrue(response.data.TMDB_API_KEY_CONFIGURED)
        self.assertEqual(response.data.TMDB_API_KEY_MASKED, "fil***890")
        self.assertEqual(response.data.QUARK_TRANSFER_COOKIE_MASKED, "fil***ide")


if __name__ == "__main__":
    unittest.main()
