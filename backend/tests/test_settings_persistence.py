import asyncio
import os
import sys
import tempfile
import unittest
from pathlib import Path
from pydantic import ValidationError

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
        self.default_env_path = Path(self.temp_dir.name) / "default.env"
        self.default_env_path.write_text("", encoding="utf-8")
        self.original_values = {
            "QSM_ENV_FILE": os.environ.get("QSM_ENV_FILE"),
            "QSM_RUNTIME_ENV_FILE": os.environ.get("QSM_RUNTIME_ENV_FILE"),
            "API_KEY": os.environ.get("API_KEY"),
            "TMDB_API_KEY": os.environ.get("TMDB_API_KEY"),
            "QUARK_TRANSFER_COOKIE": os.environ.get("QUARK_TRANSFER_COOKIE"),
            "LOG_LEVEL": os.environ.get("LOG_LEVEL"),
            "CORS_ORIGINS": os.environ.get("CORS_ORIGINS"),
        }
        os.environ["QSM_ENV_FILE"] = str(self.default_env_path)
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

    def _load_settings_with_cors(self, cors_origins: str):
        os.environ["CORS_ORIGINS"] = cors_origins
        self.runtime_env_path.write_text("", encoding="utf-8")
        get_settings.cache_clear()
        return get_settings()

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

    def test_legacy_quark_cookie_alias_points_to_transfer_cookie(self):
        self.runtime_env_path.write_text(
            "\n".join(
                [
                    "TMDB_API_KEY=file-tmdb-api-key-67890",
                    "QUARK_TRANSFER_COOKIE=file-cookie=override",
                    "",
                ]
            ),
            encoding="utf-8",
        )

        get_settings.cache_clear()
        settings = get_settings()

        self.assertEqual(settings.quark_cookie, "file-cookie=override")
        self.assertEqual(settings.quark_cookie, settings.quark_transfer_cookie)

    def test_settings_support_minimal_runtime_env(self):
        os.environ.pop("TMDB_API_KEY", None)
        os.environ.pop("QUARK_TRANSFER_COOKIE", None)
        self.runtime_env_path.write_text("", encoding="utf-8")

        get_settings.cache_clear()
        settings = get_settings()

        self.assertIsNone(settings.tmdb_api_key)
        self.assertIsNone(settings.quark_transfer_cookie)

    def test_trusted_proxy_ips_supports_comma_separated_env(self):
        os.environ["TRUSTED_PROXY_IPS"] = "127.0.0.1,::1"
        self.runtime_env_path.write_text("", encoding="utf-8")

        get_settings.cache_clear()
        settings = get_settings()

        self.assertEqual(settings.trusted_proxy_ips, ["127.0.0.1", "::1"])

    def test_trusted_proxy_ips_supports_bracketed_non_json_env(self):
        os.environ["TRUSTED_PROXY_IPS"] = "[127.0.0.1, ::1]"
        self.runtime_env_path.write_text("", encoding="utf-8")

        get_settings.cache_clear()
        settings = get_settings()

        self.assertEqual(settings.trusted_proxy_ips, ["127.0.0.1", "::1"])

    def test_trusted_proxy_ips_are_normalized_and_deduplicated(self):
        os.environ["TRUSTED_PROXY_IPS"] = "127.0.0.1,127.0.0.1, [::1] , ::1"
        self.runtime_env_path.write_text("", encoding="utf-8")

        get_settings.cache_clear()
        settings = get_settings()

        self.assertEqual(settings.trusted_proxy_ips, ["127.0.0.1", "::1"])

    def test_trusted_proxy_ips_rejects_invalid_ip(self):
        os.environ["TRUSTED_PROXY_IPS"] = "127.0.0.1,bad-ip"
        self.runtime_env_path.write_text("", encoding="utf-8")

        get_settings.cache_clear()
        with self.assertRaises(ValidationError):
            get_settings()

    def test_trusted_proxy_ips_supports_comma_separated_in_default_env_file(self):
        os.environ.pop("TRUSTED_PROXY_IPS", None)
        self.default_env_path.write_text("TRUSTED_PROXY_IPS=127.0.0.1,::1\n", encoding="utf-8")
        self.runtime_env_path.write_text("", encoding="utf-8")

        get_settings.cache_clear()
        settings = get_settings()

        self.assertEqual(settings.trusted_proxy_ips, ["127.0.0.1", "::1"])

    def test_trusted_proxy_ips_supports_comma_separated_in_runtime_env_file(self):
        os.environ.pop("TRUSTED_PROXY_IPS", None)
        self.default_env_path.write_text("", encoding="utf-8")
        self.runtime_env_path.write_text("TRUSTED_PROXY_IPS=127.0.0.1,::1\n", encoding="utf-8")

        get_settings.cache_clear()
        settings = get_settings()

        self.assertEqual(settings.trusted_proxy_ips, ["127.0.0.1", "::1"])

    def test_validate_production_security_flags_insecure_cors_origins(self):
        for cors_origins in [
            '["http://localhost:5173"]',
            '["http://127.0.0.1:5173"]',
            '["http://[::1]:5173"]',
            '["*"]',
        ]:
            with self.subTest(cors_origins=cors_origins):
                settings = self._load_settings_with_cors(cors_origins)
                warnings = settings.validate_production_security()
                self.assertIn("生产环境 CORS 配置包含不安全的源", warnings)

    def test_validate_production_security_accepts_public_cors_origins(self):
        settings = self._load_settings_with_cors('["https://example.com","https://app.example.com"]')

        warnings = settings.validate_production_security()

        self.assertNotIn("生产环境 CORS 配置包含不安全的源", warnings)


if __name__ == "__main__":
    unittest.main()
