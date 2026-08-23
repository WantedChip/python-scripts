import contextlib
import io
import subprocess  # nosec B404
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from main import (
    DEFAULT_IGNORES,
    FileDiffResult,
    HotfixReport,
    HotfixScanner,
    create_patch_file,
    main,
    parse_args,
)


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


class TestIgnoreAndListing(unittest.TestCase):
    """Tests for ignore-pattern matching and file enumeration edge cases."""

    def setUp(self) -> None:
        """Create a fresh temporary root for each test."""
        self.temp_dir = tempfile.TemporaryDirectory()
        self.base_path = Path(self.temp_dir.name)

    def tearDown(self) -> None:
        """Remove the temporary root."""
        self.temp_dir.cleanup()

    def test_is_ignored_matches_directory_part(self) -> None:
        """A bare directory pattern matches any path component."""
        scanner = HotfixScanner(
            self.base_path, self.base_path, ignore_patterns=["node_modules"]
        )
        self.assertTrue(scanner.is_ignored("web/node_modules/pkg/index.js"))
        self.assertFalse(scanner.is_ignored("web/src/pkg/index.js"))

    def test_is_ignored_matches_full_relative_path(self) -> None:
        """Wildcard patterns match the full posix relative path."""
        scanner = HotfixScanner(
            self.base_path, self.base_path, ignore_patterns=["dist/*"]
        )
        self.assertTrue(scanner.is_ignored("dist/bundle.js"))
        self.assertFalse(scanner.is_ignored("src/dist_like.js"))

    def test_get_all_relative_files_missing_base_dir(self) -> None:
        """A non-existent base directory yields an empty path set."""
        scanner = HotfixScanner(self.base_path, self.base_path)
        missing = self.base_path / "does_not_exist"
        self.assertEqual(scanner.get_all_relative_files(missing), set())

    def test_default_ignores_exclude_artifacts(self) -> None:
        """Default ignore list keeps logs, caches and archives out of the scan."""
        repo = self.base_path / "repo"
        deployed = self.base_path / "deployed"
        deployed.mkdir()
        repo.mkdir()
        (repo / "app.py").write_text("print('x')", encoding="utf-8")
        (deployed / "app.py").write_text("print('hotfix')", encoding="utf-8")
        (deployed / "crash.log").write_text("boom", encoding="utf-8")
        cache = deployed / "__pycache__"
        cache.mkdir()
        (cache / "app.cpython.pyc").write_text("bytecode", encoding="utf-8")
        (deployed / "bundle.zip").write_text("PK", encoding="utf-8")

        report = HotfixScanner(repo, deployed).scan()

        flagged = {d.relative_path for d in report.diffs}
        self.assertEqual(flagged, {"app.py"})


class TestDiffStatuses(unittest.TestCase):
    """Tests for DEPLOYED_ONLY / MISSING_IN_DEPLOYMENT and read failures."""

    def setUp(self) -> None:
        """Create paired repo/deployed directories for each test."""
        self.temp_dir = tempfile.TemporaryDirectory()
        self.base_path = Path(self.temp_dir.name)
        self.repo_dir = self.base_path / "repo"
        self.deployed_dir = self.base_path / "deployed"
        self.repo_dir.mkdir()
        self.deployed_dir.mkdir()

    def tearDown(self) -> None:
        """Remove the temporary tree."""
        self.temp_dir.cleanup()

    def test_deployed_only_file_flagged(self) -> None:
        """A file present only in deployment is reported as DEPLOYED_ONLY."""
        (self.repo_dir / "keep.py").write_text("a = 1\n", encoding="utf-8")
        (self.deployed_dir / "emergency_fix.py").write_text("b = 2\n", encoding="utf-8")

        report = HotfixScanner(self.repo_dir, self.deployed_dir).scan()

        by_status = {d.status: d for d in report.diffs}
        self.assertIn("DEPLOYED_ONLY", by_status)
        deployed_only = by_status["DEPLOYED_ONLY"]
        self.assertEqual(deployed_only.relative_path, "emergency_fix.py")
        self.assertIn("+b = 2", deployed_only.patch)

    def test_missing_in_deployment_file_flagged(self) -> None:
        """A repo file absent from deployment is MISSING_IN_DEPLOYMENT."""
        (self.repo_dir / "feature.py").write_text("c = 3\n", encoding="utf-8")

        report = HotfixScanner(self.repo_dir, self.deployed_dir).scan()

        self.assertEqual(len(report.diffs), 1)
        diff = report.diffs[0]
        self.assertEqual(diff.status, "MISSING_IN_DEPLOYMENT")
        self.assertEqual(diff.relative_path, "feature.py")
        self.assertIn("-c = 3", diff.patch)

    def test_unreadable_common_file_skipped(self) -> None:
        """Files that cannot be read in both trees are skipped silently."""

        def raise_oserror(self: Path, *args: object, **kwargs: object) -> str:
            """Simulate an I/O failure for every text read."""
            raise OSError("disk error")

        (self.repo_dir / "locked.bin").write_text("old", encoding="utf-8")
        (self.deployed_dir / "locked.bin").write_text("new", encoding="utf-8")
        with mock.patch.object(Path, "read_text", raise_oserror):
            report = HotfixScanner(self.repo_dir, self.deployed_dir).scan()

        self.assertEqual(report.diffs, [])

    def test_deployed_only_read_failure_yields_empty_content(self) -> None:
        """An unreadable deployed-only entry still produces empty-content diff."""

        def raise_oserror(self: Path, *args: object, **kwargs: object) -> str:
            """Simulate an I/O failure for every text read."""
            raise OSError("permission denied")

        (self.deployed_dir / "orphan.py").write_text("x = 1\n", encoding="utf-8")
        with mock.patch.object(Path, "read_text", raise_oserror):
            report = HotfixScanner(self.repo_dir, self.deployed_dir).scan()

        self.assertEqual(len(report.diffs), 1)
        self.assertEqual(report.diffs[0].status, "DEPLOYED_ONLY")
        self.assertEqual(report.diffs[0].deployed_content, "")

    def test_repo_only_read_failure_yields_empty_content(self) -> None:
        """An unreadable repo-only entry still produces empty-content diff."""

        def raise_oserror(self: Path, *args: object, **kwargs: object) -> str:
            """Simulate an I/O failure for every text read."""
            raise OSError("permission denied")

        (self.repo_dir / "gone.py").write_text("y = 2\n", encoding="utf-8")
        with mock.patch.object(Path, "read_text", raise_oserror):
            report = HotfixScanner(self.repo_dir, self.deployed_dir).scan()

        self.assertEqual(len(report.diffs), 1)
        self.assertEqual(report.diffs[0].status, "MISSING_IN_DEPLOYMENT")
        self.assertEqual(report.diffs[0].repo_content, "")


class TestReportDataclass(unittest.TestCase):
    """Tests for report dataclass helpers."""

    def test_has_hotfixes_reflects_diffs(self) -> None:
        """has_hotfixes is False until at least one diff is appended."""
        report = HotfixReport(repo_path="r", deployed_path="d")
        self.assertFalse(report.has_hotfixes)
        report.diffs.append(FileDiffResult(relative_path="a.py", status="MODIFIED"))
        self.assertTrue(report.has_hotfixes)


class TestParseArgs(unittest.TestCase):
    """Tests for CLI argument parsing of both subcommands."""

    def test_scan_parses_repo_deployed_and_custom_ignore(self) -> None:
        """scan accepts --repo/--deployed plus custom --ignore patterns."""
        args = parse_args(
            [
                "scan",
                "--repo",
                "/srv/repo",
                "--deployed",
                "/srv/app",
                "--ignore",
                "*.log",
                "*.tmp",
            ]
        )
        self.assertEqual(args.command, "scan")
        self.assertEqual(args.repo, "/srv/repo")
        self.assertEqual(args.deployed, "/srv/app")
        self.assertEqual(args.ignore, ["*.log", "*.tmp"])

    def test_ignore_defaults_to_builtin_patterns(self) -> None:
        """Omitting --ignore falls back to DEFAULT_IGNORES."""
        args = parse_args(["scan", "--repo", "r", "--deployed", "d"])
        self.assertEqual(args.ignore, DEFAULT_IGNORES)

    def test_patch_requires_output_and_parses(self) -> None:
        """patch parses --repo/--deployed/--output."""
        args = parse_args(
            [
                "patch",
                "--repo",
                "r",
                "--deployed",
                "d",
                "--output",
                "fix.patch",
            ]
        )
        self.assertEqual(args.command, "patch")
        self.assertEqual(args.output, "fix.patch")

    def test_missing_subcommand_leaves_command_unset(self) -> None:
        """Bare invocation parses fine but leaves command unset for main()."""
        args = parse_args([])
        self.assertIsNone(args.command)

    def test_missing_required_flag_exits(self) -> None:
        """scan without --repo exits via argparse error."""
        with contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit):
                parse_args(["scan", "--deployed", "d"])


class TestMainEntrypoint(unittest.TestCase):
    """End-to-end tests for main() using temporary directory trees."""

    def setUp(self) -> None:
        """Create paired repo/deployed trees used by the CLI tests."""
        self.temp_dir = tempfile.TemporaryDirectory()
        self.base_path = Path(self.temp_dir.name)
        self.repo_dir = self.base_path / "repo"
        self.deployed_dir = self.base_path / "deployed"
        self.repo_dir.mkdir()
        self.deployed_dir.mkdir()
        (self.repo_dir / "app.py").write_text("print('hi')\n", encoding="utf-8")
        (self.deployed_dir / "app.py").write_text("print('hi')\n", encoding="utf-8")

    def tearDown(self) -> None:
        """Remove the temporary trees."""
        self.temp_dir.cleanup()

    def _main_output(self, argv: list) -> tuple:
        """Run main(argv); return (exit code, stdout text)."""
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            code = main(argv)
        return code, stdout.getvalue()

    def test_no_command_reports_usage_error_code(self) -> None:
        """Invoking without a sub-command returns exit code 1."""
        code, out = self._main_output([])
        self.assertEqual(code, 1)
        self.assertEqual(out, "")

    def test_scan_clean_tree_returns_zero(self) -> None:
        """Identical trees produce the all-clear message and exit 0."""
        code, out = self._main_output(
            [
                "scan",
                "--repo",
                str(self.repo_dir),
                "--deployed",
                str(self.deployed_dir),
            ]
        )
        self.assertEqual(code, 0)
        self.assertIn("No hotfix debt detected", out)

    def test_scan_drifted_tree_lists_discrepancies(self) -> None:
        """Drifted files are listed per status and exit code is 1."""
        (self.deployed_dir / "app.py").write_text(
            "print('hotfixed')\n", encoding="utf-8"
        )
        (self.deployed_dir / "extra.py").write_text("z = 9\n", encoding="utf-8")
        code, out = self._main_output(
            [
                "scan",
                "--repo",
                str(self.repo_dir),
                "--deployed",
                str(self.deployed_dir),
            ]
        )
        self.assertEqual(code, 1)
        self.assertIn("[MODIFIED] app.py", out)
        self.assertIn("[DEPLOYED_ONLY] extra.py", out)

    def test_patch_command_writes_candidate_patch(self) -> None:
        """patch writes a unified diff file and reports its location."""
        (self.deployed_dir / "app.py").write_text(
            "print('hotfixed')\n", encoding="utf-8"
        )
        output = self.base_path / "candidate.patch"
        code, out = self._main_output(
            [
                "patch",
                "--repo",
                str(self.repo_dir),
                "--deployed",
                str(self.deployed_dir),
                "--output",
                str(output),
            ]
        )
        self.assertEqual(code, 0)
        self.assertTrue(output.exists())
        self.assertIn("Generated patch for 1 files", out)
        patch_text = output.read_text(encoding="utf-8")
        self.assertIn("--- a/app.py", patch_text)
        self.assertIn("+++ b/app.py", patch_text)

    def test_script_main_guard_runs_cli(self) -> None:
        """Running the script file end-to-end scans a clean tree and exits 0."""
        script = Path(__file__).resolve().parent.parent / "main.py"
        proc = subprocess.run(  # nosec B603
            [
                sys.executable,
                str(script),
                "scan",
                "--repo",
                str(self.repo_dir),
                "--deployed",
                str(self.deployed_dir),
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(proc.returncode, 0)
        self.assertIn("No hotfix debt detected", proc.stdout)


if __name__ == "__main__":
    unittest.main()
