import shutil
import tempfile
import unittest
from pathlib import Path

from main import BundleSanitizer


class TestBundleSanitizer(unittest.TestCase):
    def setUp(self):
        repls = {"secret_name": "[CUSTOM_NAME]"}
        self.sanitizer = BundleSanitizer(custom_replacements=repls)
        self.temp_dir = tempfile.mkdtemp()
        self.src_dir = Path(self.temp_dir) / "src"
        self.dst_dir = Path(self.temp_dir) / "dst"
        self.src_dir.mkdir()

    def tearDown(self):
        shutil.rmtree(self.temp_dir)

    def test_sanitize_text_deterministic(self):
        sample = (
            "Contact dev@example.com or admin@example.com. "
            "Again dev@example.com. IP: 10.0.0.5 and 10.0.0.5. "
            "Path: /home/devuser/config. secret_name is key."
        )
        sanitized = self.sanitizer.sanitize_text(sample)
        self.assertIn("[EMAIL_1]", sanitized)
        self.assertIn("[EMAIL_2]", sanitized)
        self.assertIn("[IP_1]", sanitized)
        self.assertIn("[PATH_1]", sanitized)
        self.assertIn("[CUSTOM_NAME]", sanitized)

        # Verify determinism: dev@example.com mapped to [EMAIL_1] twice
        self.assertEqual(sanitized.count("[EMAIL_1]"), 2)
        self.assertEqual(sanitized.count("[IP_1]"), 2)

    def test_secret_redaction(self):
        sample = "api_key='secret12345678' Bearer eyJhbGci.eyJzdWI.sig"
        sanitized = self.sanitizer.sanitize_text(sample)
        self.assertIn("[REDACTED_SECRET]", sanitized)
        self.assertIn("[REDACTED_TOKEN]", sanitized)

    def test_directory_sanitization(self):
        sub_folder = self.src_dir / "logs"
        sub_folder.mkdir()
        log_file = sub_folder / "app.log"
        log_text = "User email user@test.org logged in from 172.16.0.1"
        log_file.write_text(log_text, encoding="utf-8")

        binary_file = sub_folder / "image.bin"
        binary_file.write_bytes(b"\x00\x01\x02\x03\x04")

        s_cnt, t_cnt = self.sanitizer.sanitize_directory(self.src_dir, self.dst_dir)
        self.assertEqual(t_cnt, 2)
        self.assertEqual(s_cnt, 1)

        dst_log = self.dst_dir / "logs" / "app.log"
        self.assertTrue(dst_log.exists())
        content = dst_log.read_text(encoding="utf-8")
        self.assertIn("[EMAIL_1]", content)
        self.assertIn("[IP_1]", content)

        dst_bin = self.dst_dir / "logs" / "image.bin"
        self.assertTrue(dst_bin.exists())
        self.assertEqual(dst_bin.read_bytes(), b"\x00\x01\x02\x03\x04")


if __name__ == "__main__":
    unittest.main()
