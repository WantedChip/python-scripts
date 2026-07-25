import tempfile
import unittest
from pathlib import Path

from main import HotfixScanner, create_patch_file


class TestHotfixDebt(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.base_path = Path(self.temp_dir.name)
        self.repo_dir = self.base_path / "repo"
        self.deployed_dir = self.base_path / "deployed"

        self.repo_dir.mkdir()
        self.deployed_dir.mkdir()

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_identical_directories(self):
        (self.repo_dir / "app.py").write_text("print('hello')", encoding="utf-8")
        (self.deployed_dir / "app.py").write_text("print('hello')", encoding="utf-8")

        scanner = HotfixScanner(self.repo_dir, self.deployed_dir)
        report = scanner.scan()

        self.assertFalse(report.has_hotfixes)
        self.assertEqual(len(report.diffs), 0)

    def test_modified_deployed_file(self):
        (self.repo_dir / "app.py").write_text("print('hello')", encoding="utf-8")
        (self.deployed_dir / "app.py").write_text(
            "print('hello hotfix')", encoding="utf-8"
        )

        scanner = HotfixScanner(self.repo_dir, self.deployed_dir)
        report = scanner.scan()

        self.assertTrue(report.has_hotfixes)
        self.assertEqual(len(report.diffs), 1)
        self.assertEqual(report.diffs[0].relative_path, "app.py")
        self.assertEqual(report.diffs[0].status, "MODIFIED")
        self.assertIn("hotfix", report.diffs[0].patch)

    def test_ignore_patterns(self):
        (self.repo_dir / "app.py").write_text("print('hello')", encoding="utf-8")
        (self.deployed_dir / "app.py").write_text("print('hello')", encoding="utf-8")

        (self.deployed_dir / "server.log").write_text("log data", encoding="utf-8")

        scanner = HotfixScanner(
            self.repo_dir, self.deployed_dir, ignore_patterns=["*.log"]
        )
        report = scanner.scan()

        self.assertFalse(report.has_hotfixes)

    def test_patch_file_creation(self):
        (self.repo_dir / "config.json").write_text('{"env": "dev"}', encoding="utf-8")
        (self.deployed_dir / "config.json").write_text(
            '{"env": "prod"}', encoding="utf-8"
        )

        scanner = HotfixScanner(self.repo_dir, self.deployed_dir)
        report = scanner.scan()

        patch_file = self.base_path / "test.patch"
        create_patch_file(report, patch_file)

        self.assertTrue(patch_file.exists())
        content = patch_file.read_text(encoding="utf-8")
        self.assertIn("a/config.json", content)
        self.assertIn("b/config.json", content)


if __name__ == "__main__":
    unittest.main()
