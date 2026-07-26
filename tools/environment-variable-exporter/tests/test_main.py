"""Unit tests for Environment Variable Exporter."""

import os
import tempfile
import unittest

from main import (
    export_env_file,
    filter_environment_variables,
    generate_env_file_content,
    is_secret_key,
    sanitize_value,
)


class TestEnvironmentVariableExporter(unittest.TestCase):

    def test_is_secret_key(self) -> None:
        self.assertTrue(is_secret_key("DATABASE_PASSWORD"))
        self.assertTrue(is_secret_key("API_KEY"))
        self.assertTrue(is_secret_key("JWT_SECRET_TOKEN"))
        self.assertFalse(is_secret_key("APP_HOST"))
        self.assertFalse(is_secret_key("PORT"))

    def test_filter_environment_variables_prefix(self) -> None:
        fake_env = {
            "APP_NAME": "MyApp",
            "APP_PORT": "8080",
            "DB_HOST": "localhost",
        }
        res = filter_environment_variables(prefix="APP_", environ=fake_env)
        self.assertEqual(len(res), 2)
        self.assertIn("APP_NAME", res)
        self.assertIn("APP_PORT", res)
        self.assertNotIn("DB_HOST", res)

    def test_filter_environment_variables_keys(self) -> None:
        fake_env = {
            "APP_NAME": "MyApp",
            "DB_HOST": "localhost",
            "DB_USER": "postgres",
        }
        res = filter_environment_variables(
            keys=["APP_NAME", "DB_USER"], environ=fake_env
        )
        self.assertEqual(len(res), 2)
        self.assertIn("APP_NAME", res)
        self.assertIn("DB_USER", res)

    def test_sanitize_value_masking(self) -> None:
        val = sanitize_value(
            "API_SECRET_KEY",
            "super_secret_123",
            mask_secrets=True,
            placeholder="SECRET",
        )
        self.assertEqual(val, "<SECRET>")

        val_normal = sanitize_value("APP_ENV", "production", mask_secrets=True)
        self.assertEqual(val_normal, "production")

    def test_generate_env_file_content(self) -> None:
        env_dict = {"APP_PORT": "3000", "DB_PASS": "pass123"}
        content = generate_env_file_content(env_dict, mask_secrets=True)
        self.assertIn("APP_PORT=3000\n", content)
        self.assertIn("DB_PASS=<YOUR_VALUE_HERE>\n", content)

    def test_export_env_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            out_file = os.path.join(tmp_dir, "test.env")
            mock_env = {"TEST_KEY_1": "val1", "TEST_KEY_2": "val2"}
            with unittest.mock.patch.dict(os.environ, mock_env):
                count = export_env_file(out_file, prefix="TEST_KEY_")
                self.assertEqual(count, 2)
                self.assertTrue(os.path.exists(out_file))


if __name__ == "__main__":
    unittest.main()
