import contextlib
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from typing import Any, Callable, List, Tuple
from unittest.mock import MagicMock, patch

from main import CommandProfiler, build_parser, main


class TestDirtyGenerator(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root_dir = Path(self.temp_dir.name)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_profile_command_creates_file(self):
        # Use forward slashes so the injected -c snippet stays valid Python
        # regardless of Windows backslash escape sequences in temp paths.
        target = (self.root_dir / "out.tmp").as_posix()
        cmd = f"python -c \"open('{target}', 'w').write('test')\""

        profiler = CommandProfiler(self.root_dir)
        report = profiler.profile_command(cmd)

        self.assertTrue(report.is_dirty)
        self.assertIn("out.tmp", report.created_files)

    def test_baseline_recording_and_validation(self):
        baseline_file = self.root_dir / "baseline.json"
        # Use forward slashes so the injected -c snippet stays valid Python
        # regardless of Windows backslash escape sequences in temp paths.
        log_path = (self.root_dir / "build.log").as_posix()
        cmd = f"python -c \"open('{log_path}', 'w').write('done')\""

        profiler = CommandProfiler(self.root_dir, baseline_path=baseline_file)
        report1 = profiler.profile_command(cmd, record_as_baseline=True)

        # The recording run itself still reports the observed mutation...
        self.assertEqual(len(report1.violations), 1)
        self.assertTrue(baseline_file.exists())

        # Second run should match baseline and have 0 violations
        report2 = profiler.profile_command(cmd)
        self.assertEqual(len(report2.violations), 0)


def _fs_side_effect(actions: Callable[[], None]) -> Any:
    """Builds a ``subprocess.run`` stand-in that mutates files then returns."""

    def _runner(*_args: Any, **_kwargs: Any) -> MagicMock:
        actions()
        return MagicMock(returncode=0)

    return _runner


class TestMutationDetection(unittest.TestCase):
    """Created/modified/deleted detection around a faked command."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.root = Path(self.temp_dir.name)
        (self.root / "existing.txt").write_text("v1")
        (self.root / "doomed.txt").write_text("bye")

    def test_all_mutation_kinds_are_classified(self) -> None:
        profiler = CommandProfiler(self.root)

        def mutate() -> None:
            (self.root / "existing.txt").write_text("version-two-longer")
            (self.root / "fresh.log").write_text("new")
            (self.root / "doomed.txt").unlink()

        with patch(
            "main.subprocess.run", side_effect=_fs_side_effect(mutate)
        ) as mock_run:
            report = profiler.profile_command("fake-build")

        mock_run.assert_called_once()
        self.assertEqual(report.created_files, ["fresh.log"])
        self.assertEqual(report.modified_files, ["existing.txt"])
        self.assertEqual(report.deleted_files, ["doomed.txt"])
        self.assertTrue(report.is_dirty)
        self.assertGreaterEqual(report.execution_time_seconds, 0.0)

    def test_noop_command_is_not_dirty(self) -> None:
        profiler = CommandProfiler(self.root)
        with patch("main.subprocess.run", side_effect=_fs_side_effect(lambda: None)):
            report = profiler.profile_command("noop")
        self.assertFalse(report.is_dirty)
        self.assertEqual(report.violations, [])


class TestViolationsAndBaselines(unittest.TestCase):
    """Baseline storage and violation computation rules."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.root = Path(self.temp_dir.name)
        self.baseline_file = self.root / "baseline.json"

    def _profiler_with_allowlist(self, patterns: List[str]) -> CommandProfiler:
        profiler = CommandProfiler(self.root, baseline_path=self.baseline_file)
        profiler.baselines["build"] = patterns
        return profiler

    def test_every_mutation_violates_without_baseline(self) -> None:
        (self.root / "seed.txt").write_text("x")
        profiler = CommandProfiler(self.root)

        def mutate() -> None:
            (self.root / "untracked.bin").write_text("data")

        with patch("main.subprocess.run", side_effect=_fs_side_effect(mutate)):
            report = profiler.profile_command("build")

        self.assertIn("untracked.bin", report.violations)

    def test_matching_pattern_suppresses_violation(self) -> None:
        profiler = self._profiler_with_allowlist(["generated/*.log"])

        def mutate() -> None:
            gen = self.root / "generated"
            gen.mkdir()
            (gen / "run.log").write_text("ok")

        with patch("main.subprocess.run", side_effect=_fs_side_effect(mutate)):
            report = profiler.profile_command("build")
        self.assertEqual(report.violations, [])

    def test_record_as_baseline_persists_sorted_mutations(self) -> None:
        profiler = CommandProfiler(self.root, baseline_path=self.baseline_file)

        def mutate() -> None:
            (self.root / "b_artifact.txt").write_text("1")
            (self.root / "a_artifact.txt").write_text("2")

        with patch("main.subprocess.run", side_effect=_fs_side_effect(mutate)):
            report = profiler.profile_command("build", record_as_baseline=True)

        self.assertEqual(
            profiler.baselines["build"], ["a_artifact.txt", "b_artifact.txt"]
        )
        stored = json.loads(self.baseline_file.read_text(encoding="utf-8"))
        self.assertEqual(
            stored["commands"]["build"], ["a_artifact.txt", "b_artifact.txt"]
        )
        # The recording run itself still flags violations for transparency.
        self.assertEqual(len(report.violations), 2)

    def test_corrupt_baseline_file_loads_empty(self) -> None:
        self.baseline_file.write_text("{not json", encoding="utf-8")
        profiler = CommandProfiler(self.root, baseline_path=self.baseline_file)
        self.assertEqual(profiler.baselines, {})

    def test_non_mapping_commands_section_loads_empty(self) -> None:
        self.baseline_file.write_text('{"commands": [1, 2]}', encoding="utf-8")
        profiler = CommandProfiler(self.root, baseline_path=self.baseline_file)
        self.assertEqual(profiler.baselines, {})

    def test_save_without_baseline_path_is_harmless_noop(self) -> None:
        profiler = CommandProfiler(self.root)
        profiler.save_baselines()
        self.assertIsNone(profiler.baseline_path)


class TestPatternMatching(unittest.TestCase):
    """fnmatch semantics for allowed mutation patterns."""

    def setUp(self) -> None:
        self.profiler = CommandProfiler(Path(tempfile.gettempdir()))

    def test_matches_full_posix_path_pattern(self) -> None:
        self.assertTrue(
            self.profiler.is_pattern_matched("logs/run-01.log", ["logs/*.log"])
        )

    def test_matches_bare_filename_pattern(self) -> None:
        self.assertTrue(
            self.profiler.is_pattern_matched("deep/nested/out.tmp", ["*.tmp"])
        )

    def test_unrelated_paths_do_not_match(self) -> None:
        self.assertFalse(self.profiler.is_pattern_matched("src/app.py", ["*.tmp"]))


class TestCliEntrypoint(unittest.TestCase):
    """End-to-end CLI runs inside an isolated temporary working dir."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.prev_cwd = os.getcwd()
        os.chdir(self.temp_dir.name)
        self.addCleanup(os.chdir, self.prev_cwd)

    def _make_cmd(self, filename: str, content: str = "out") -> str:
        target = (Path.cwd() / filename).as_posix()
        return f"python -c \"open('{target}', 'w').write('{content}')\""

    def _run_cli(self, args: List[str]) -> Tuple[int, str]:
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            exit_code = main(args)
        return exit_code, buffer.getvalue()

    def test_clean_command_exits_zero(self) -> None:
        code, out = self._run_cli(["--cmd", 'python -c "pass"', "--root", "."])
        self.assertEqual(code, 0)
        self.assertIn("Filesystem Dirty: False", out)

    def test_unbaselined_mutations_exit_one_with_alerts(self) -> None:
        code, out = self._run_cli(["--cmd", self._make_cmd("stray.txt"), "--root", "."])
        self.assertEqual(code, 1)
        self.assertIn("[ALERT] Baseline Violations (1):", out)
        self.assertIn("! stray.txt", out)
        self.assertIn("+ stray.txt", out)

    def test_recorded_baseline_makes_second_run_clean(self) -> None:
        baseline = "base.json"
        cmd = self._make_cmd("known.txt")
        code_first, out_first = self._run_cli(
            [
                "--cmd",
                cmd,
                "--root",
                ".",
                "--baseline-file",
                baseline,
                "--record-baseline",
            ]
        )
        self.assertEqual(code_first, 1)  # recording run still alerts
        self.assertIn("+ known.txt", out_first)
        self.assertIn("[ALERT] Baseline Violations (1):", out_first)

        code_second, out_second = self._run_cli(
            ["--cmd", cmd, "--root", ".", "--baseline-file", baseline]
        )
        self.assertEqual(code_second, 0)
        self.assertNotIn("[ALERT]", out_second)
        self.assertTrue(Path(baseline).exists())

    def test_report_lists_modified_and_deleted_sections(self) -> None:
        Path("old.txt").write_text("keep")
        Path("mutate_me.txt").write_text("before")
        script = (
            "import pathlib;"
            "pathlib.Path('mutate_me.txt').write_text('after-much-longer');"
            "pathlib.Path('old.txt').unlink()"
        )
        code, out = self._run_cli(["--cmd", f'python -c "{script}"', "--root", "."])
        self.assertEqual(code, 1)
        self.assertIn("~ mutate_me.txt", out)
        self.assertIn("- old.txt", out)


class TestParserRequirements(unittest.TestCase):
    """Argument parser contract."""

    def test_cmd_flag_is_required(self) -> None:
        with self.assertRaises(SystemExit):
            build_parser().parse_args([])


if __name__ == "__main__":
    unittest.main()
