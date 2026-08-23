"""Unit tests for file-share-audit main.py."""

import contextlib
import importlib
import io
import os
import sys
import tempfile
import unittest
from unittest import mock

import main as main_module
from main import AuditReport, FileShareAuditor, main


def _write(path: str, content: str) -> None:
    """Write ``content`` to ``path`` creating parent dirs if needed."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)


class TestFileShareAuditor(unittest.TestCase):

    def test_detect_sensitive_env_file_and_secret(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create a mock .env file with an API key
            env_path = os.path.join(tmpdir, ".env")
            with open(env_path, "w", encoding="utf-8") as f:
                f.write("OPENAI_KEY=sk-abc123xyz45678901234567890123456\n")

            auditor = FileShareAuditor(username="testuser")
            report = auditor.audit_directory(tmpdir)

            self.assertGreaterEqual(report.high_count, 1)
            categories = [finding.category for finding in report.findings]
            self.assertIn("Sensitive File", categories)

    def test_detect_username_in_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            user_subdir = os.path.join(tmpdir, "testuser_data")
            os.makedirs(user_subdir, exist_ok=True)
            dummy_file = os.path.join(user_subdir, "sample.txt")
            with open(dummy_file, "w", encoding="utf-8") as f:
                f.write("Clean content")

            auditor = FileShareAuditor(username="testuser")
            report = auditor.audit_directory(tmpdir)

            categories = [finding.category for finding in report.findings]
            self.assertIn("Username Exposure", categories)

    def test_clean_directory(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            clean_file = os.path.join(tmpdir, "readme.txt")
            with open(clean_file, "w", encoding="utf-8") as f:
                f.write("Hello world, this is clean public documentation.")

            auditor = FileShareAuditor(username="nonexistentuser")
            report = auditor.audit_directory(tmpdir)

            self.assertEqual(len(report.findings), 0)


class TestDirectoryStructureFindings(unittest.TestCase):
    """Tests for git folders, hidden entries, and log file detection."""

    def test_git_and_hidden_directories_flagged(self) -> None:
        """Exposed .git and dot-directories produce their own findings."""
        with tempfile.TemporaryDirectory() as tmpdir:
            _write(os.path.join(tmpdir, ".git", "HEAD"), "ref: refs/heads/main")
            _write(os.path.join(tmpdir, ".idea", "misc.xml"), "<xml/>")
            report = FileShareAuditor(username="-").audit_directory(tmpdir)
            categories = {f.category for f in report.findings}
        self.assertIn("Git History", categories)
        self.assertIn("Hidden Directory", categories)

    def test_log_and_hidden_files_flagged(self) -> None:
        """Log files rate MEDIUM; non-gitignore hidden files rate LOW."""
        with tempfile.TemporaryDirectory() as tmpdir:
            _write(os.path.join(tmpdir, "app.log"), "2026-01-01 INFO ok")
            _write(os.path.join(tmpdir, ".hidden_cfg"), "x=1")
            _write(os.path.join(tmpdir, ".gitignore"), "*.log")
            report = FileShareAuditor(username="-").audit_directory(tmpdir)
            by_cat = {f.category: f.filepath for f in report.findings}
        self.assertIn("Private Log", by_cat)
        self.assertIn("Hidden File", by_cat)
        self.assertNotIn(".gitignore", str(by_cat.get("Hidden File", "")))

    def test_severity_count_properties(self) -> None:
        """high/medium/low counters reflect the findings list."""
        with tempfile.TemporaryDirectory() as tmpdir:
            _write(os.path.join(tmpdir, ".env"), "SECRET_KEY='abcdefgh12345678'\n")
            _write(os.path.join(tmpdir, "debug.log"), "log line\n")
            _write(os.path.join(tmpdir, ".dotfile"), "data")
            report = FileShareAuditor(username="-").audit_directory(tmpdir)
        self.assertGreaterEqual(report.high_count, 1)
        self.assertGreaterEqual(report.medium_count, 1)
        self.assertGreaterEqual(report.low_count, 1)

    def test_oversized_text_file_skipped(self) -> None:
        """Files larger than 5 MB are not scanned for secrets."""
        with tempfile.TemporaryDirectory() as tmpdir:
            big_path = os.path.join(tmpdir, "big.txt")
            with open(big_path, "wb") as f:
                f.seek(5 * 1024 * 1024 + 1)
                f.write(b"\0")
            report = FileShareAuditor(username="-").audit_directory(tmpdir)
            secret_hits = [
                f for f in report.findings if f.category == "API Key / Credential"
            ]
        self.assertEqual(secret_hits, [])


class TestExifGpsChecks(unittest.TestCase):
    """Tests for EXIF GPS detection (PIL Image fully mocked)."""

    @staticmethod
    def _image_context(getexif_return: object) -> mock.MagicMock:
        """Build a mocked PIL image usable as a context manager."""
        img_mock = mock.MagicMock()
        img_mock.__enter__.return_value = img_mock
        img_mock.getexif.return_value = getexif_return
        return img_mock

    def _audit_image(self, getexif_return: object) -> AuditReport:
        """Audit a temp dir containing one jpg with mocked EXIF data."""
        with tempfile.TemporaryDirectory() as tmpdir:
            photo = os.path.join(tmpdir, "photo.jpg")
            _write(photo, "not a real image")
            img_mock = self._image_context(getexif_return)
            with mock.patch.object(main_module, "Image") as mock_image:
                mock_image.open.return_value = img_mock
                return FileShareAuditor(username="-").audit_directory(tmpdir)

    def test_gps_metadata_flagged_high(self) -> None:
        """GPSInfo EXIF tags produce a HIGH severity finding."""
        # 34853 is the standard EXIF GPSInfo tag id.
        report = self._audit_image({34853: b"\x00\x01"})
        gps_hits = [f for f in report.findings if f.category == "EXIF GPS Data"]
        self.assertEqual(len(gps_hits), 1)
        self.assertEqual(gps_hits[0].severity, "HIGH")

    def test_non_gps_exif_not_flagged(self) -> None:
        """EXIF without GPSInfo does not trigger GPS findings."""
        report = self._audit_image({271: "CameraMaker"})
        gps_hits = [f for f in report.findings if f.category == "EXIF GPS Data"]
        self.assertEqual(gps_hits, [])

    def test_empty_exif_not_flagged(self) -> None:
        """Images without any EXIF data pass silently."""
        report = self._audit_image({})
        gps_hits = [f for f in report.findings if f.category == "EXIF GPS Data"]
        self.assertEqual(gps_hits, [])

    def test_unreadable_image_does_not_crash(self) -> None:
        """Image open failures are swallowed during audit."""
        with tempfile.TemporaryDirectory() as tmpdir:
            photo = os.path.join(tmpdir, "broken.png")
            _write(photo, "junk")
            with mock.patch.object(
                main_module.Image,
                "open",
                side_effect=OSError("cannot identify image"),
            ):
                report = FileShareAuditor(username="-").audit_directory(tmpdir)
        self.assertEqual([f for f in report.findings if "EXIF" in f.category], [])

    def test_pil_missing_falls_back_gracefully(self) -> None:
        """Without Pillow installed the module still imports and audits."""
        original_pil_available = main_module.PIL_AVAILABLE
        try:
            with mock.patch.dict(sys.modules, {"PIL": None}):
                importlib.reload(main_module)
            self.assertFalse(main_module.PIL_AVAILABLE)
            with tempfile.TemporaryDirectory() as tmpdir:
                photo = os.path.join(tmpdir, "photo.jpg")
                _write(photo, "content ignored without PIL")
                report = main_module.FileShareAuditor(username="-").audit_directory(
                    tmpdir
                )
            self.assertEqual([f for f in report.findings if "EXIF" in f.category], [])
        finally:
            importlib.reload(main_module)
            self.assertTrue(main_module.PIL_AVAILABLE)
            self.assertEqual(original_pil_available, True)


class TestPrintSummaryAndCli(unittest.TestCase):
    """Tests for report rendering and the CLI entry point."""

    def test_print_summary_with_findings(self) -> None:
        """The summary lists every finding with file and line details."""
        report = AuditReport(target_dir="C:/tmp/demo", total_files_scanned=3)
        report.findings.append(
            main_module.AuditFinding(
                filepath="a.env",
                category="Sensitive File",
                severity="HIGH",
                description="detected",
                line_number=4,
            )
        )
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            report.print_summary()
        out = buf.getvalue()
        self.assertIn("FILE SHARE AUDIT REPORT", out)
        self.assertIn("Total Files Scanned: 3", out)
        self.assertIn("(Line 4)", out)
        self.assertIn("[HIGH] Sensitive File", out)

    def test_print_summary_safe_message(self) -> None:
        """Clean scans print a SAFE message."""
        report = AuditReport(target_dir="C:/tmp/clean", total_files_scanned=1)
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            report.print_summary()
        self.assertIn("[SAFE]", buf.getvalue())

    def test_cli_runs_audit_on_directory(self) -> None:
        """main() parses args, audits the directory, prints summary."""
        with tempfile.TemporaryDirectory() as tmpdir:
            _write(os.path.join(tmpdir, ".env"), "A='0123456789abcdef'\n")
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                with mock.patch.object(sys, "argv", ["main.py", tmpdir]):
                    main()
            out = buf.getvalue()
        self.assertIn("FILE SHARE AUDIT REPORT", out)
        self.assertIn("Sensitive File", out)


if __name__ == "__main__":
    unittest.main()
