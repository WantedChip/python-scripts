"""Unit tests for config-experiment tool."""

import contextlib
import io
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock, patch

from main import (
    RunResult,
    build_parser,
    compare_results,
    generate_report,
    main,
    run_single_config,
)


class TestConfigExperiment(unittest.TestCase):
    """Test suite for config-experiment functions."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.dir_path = Path(self.temp_dir.name)

        self.cfg1 = self.dir_path / "cfg1.json"
        self.cfg1.write_text('{"mode": "debug"}', encoding="utf-8")

        self.cfg2 = self.dir_path / "cfg2.json"
        self.cfg2.write_text('{"mode": "prod"}', encoding="utf-8")

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_run_single_config(self) -> None:
        cmd = "python -c \"import os; print(os.environ.get('MY_CFG'))\""
        res = run_single_config(cmd, self.cfg1, env_var_name="MY_CFG")
        self.assertEqual(res.exit_code, 0)
        self.assertIn("cfg1.json", res.stdout)

    def test_compare_results_identical(self) -> None:
        r1 = RunResult("cfg1.json", "{}", 0, "hello\n", "", 0.1)
        r2 = RunResult("cfg2.json", "{}", 0, "hello\n", "", 0.1)
        comp = compare_results([r1, r2])

        self.assertEqual(comp["baseline_config"], "cfg1.json")
        self.assertTrue(comp["runs_summary"][0]["matches_baseline"])
        self.assertTrue(comp["runs_summary"][1]["matches_baseline"])
        self.assertEqual(len(comp["variations"]), 1)
        self.assertFalse(comp["variations"][0]["stdout_diff"])

    def test_compare_results_different(self) -> None:
        r1 = RunResult("cfg1.json", "{}", 0, "mode debug\n", "", 0.1)
        r2 = RunResult("cfg2.json", "{}", 1, "mode prod\n", "err\n", 0.2)
        comp = compare_results([r1, r2])

        self.assertFalse(comp["runs_summary"][1]["matches_baseline"])
        var = comp["variations"][0]
        self.assertTrue(var["exit_code_diff"]["changed"])
        self.assertIn("mode prod", var["stdout_diff"])

    def test_generate_report_formats(self) -> None:
        r1 = RunResult("cfg1.json", "{}", 0, "out1\n", "", 0.1)
        r2 = RunResult("cfg2.json", "{}", 0, "out2\n", "", 0.1)
        comp = compare_results([r1, r2])

        text_rep = generate_report(comp, fmt="text")
        self.assertIn("CONFIGURATION EXPERIMENT REPORT", text_rep)

        json_rep = generate_report(comp, fmt="json")
        parsed = json.loads(json_rep)
        self.assertEqual(parsed["baseline_config"], "cfg1.json")

        md_rep = generate_report(comp, fmt="markdown")
        self.assertIn("# Configuration Experiment Difference Report", md_rep)


def _mock_run(
    returncode: int = 0,
    stdout: str = "",
    stderr: str = "",
    side_effect: Optional[Exception] = None,
) -> MagicMock:
    """Builds a patched ``subprocess.run`` double for isolated runs."""
    if side_effect is not None:
        return MagicMock(side_effect=side_effect)
    proc = SimpleNamespace(returncode=returncode, stdout=stdout, stderr=stderr)
    return MagicMock(side_effect=lambda *args, **kwargs: proc)


class TestRunSingleConfigBehaviour(unittest.TestCase):
    """Isolated execution semantics of ``run_single_config``."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.dir_path = Path(self.temp_dir.name)
        self.cfg = self.dir_path / "app.json"
        self.cfg.write_text('{"flag": true}', encoding="utf-8")

    def test_placeholder_is_replaced_with_resolved_config_path(self) -> None:
        fake_run = _mock_run(returncode=0, stdout="ok")
        with patch("main.subprocess.run", new=fake_run):
            result = run_single_config("runner --cfg {config}", self.cfg)
        self.assertEqual(result.exit_code, 0)
        invoked_cmd = fake_run.call_args[0][0]
        self.assertNotIn("{config}", invoked_cmd)
        self.assertIn(str(self.cfg.resolve()), invoked_cmd)

    def test_env_variable_receives_absolute_config_path(self) -> None:
        captured: Dict[str, Any] = {}

        def fake_run(cmd: str, **kwargs: Any) -> SimpleNamespace:
            captured.update(kwargs.get("env", {}))
            return SimpleNamespace(returncode=0, stdout="env ok", stderr="")

        with patch("main.subprocess.run", new=MagicMock(side_effect=fake_run)):
            result = run_single_config("any", self.cfg, env_var_name="MY_CFG")
        self.assertEqual(captured.get("MY_CFG"), str(self.cfg.resolve()))
        self.assertIn("env ok", result.stdout)

    def test_missing_config_file_records_empty_content(self) -> None:
        ghost = self.dir_path / "ghost.json"
        with patch("main.subprocess.run", return_value=_mock_run()):
            result = run_single_config("noop", ghost)
        self.assertEqual(result.config_content, "")
        self.assertEqual(result.config_name, "ghost.json")

    def test_timeout_reports_minus_one_and_message(self) -> None:
        expired = subprocess.TimeoutExpired(cmd="slow", timeout=0.5)
        expired.stdout = b"partial"
        with patch("main.subprocess.run", side_effect=expired):
            result = run_single_config("slow-cmd", self.cfg, timeout=0.5)
        self.assertEqual(result.exit_code, -1)
        self.assertIn("timed out after 0.5 seconds", result.stderr)

    def test_os_error_reports_execution_failure(self) -> None:
        with patch("main.subprocess.run", side_effect=OSError("spawn failed")):
            result = run_single_config("broken", self.cfg)
        self.assertEqual(result.exit_code, -1)
        self.assertIn("Execution failed:", result.stderr)
        self.assertIn("spawn failed", result.stderr)


class TestCompareAndReportEdges(unittest.TestCase):
    """Comparison matrix and report rendering edge cases."""

    @staticmethod
    def _results() -> List[RunResult]:
        """Baseline plus two differing follow-up configurations."""
        baseline = RunResult("base.json", "{}", 0, "same out\n", "", 0.05)
        quiet = RunResult("quiet.json", "{}", 0, "same out\n", "", 0.04)
        loud = RunResult("loud.json", "{}", 2, "other out\n", "boom\n", 0.06)
        return [baseline, quiet, loud]

    def test_empty_results_short_circuit(self) -> None:
        self.assertEqual(compare_results([]), {"runs": [], "differences": {}})

    def test_multiple_variations_are_all_reported(self) -> None:
        comp = compare_results(self._results())
        names = [v["config_name"] for v in comp["variations"]]
        self.assertEqual(names, ["quiet.json", "loud.json"])
        self.assertTrue(comp["runs_summary"][1]["matches_baseline"])
        self.assertFalse(comp["runs_summary"][2]["matches_baseline"])

    def test_text_report_notes_no_behavioral_differences(self) -> None:
        comp = compare_results(self._results())
        text = generate_report(comp, fmt="text")
        self.assertIn("--- quiet.json ---", text)
        self.assertIn("No behavioral differences detected.", text)
        self.assertIn("Exit Code Changed: 0 -> 2", text)
        self.assertIn("DIFFERENT", text)

    def test_markdown_report_renders_tables_and_diff_blocks(self) -> None:
        comp = compare_results(self._results())
        md = generate_report(comp, fmt="markdown")
        self.assertIn("| `base.json` | 0 | 0.05 | Yes |", md)
        self.assertIn("**NO**", md)
        self.assertIn("- **Exit Code Changed:** 0 -> 2", md)
        self.assertIn("**stdout Differences:**", md)
        self.assertIn("```diff", md)
        self.assertIn("- **stderr:** Unchanged", md)


def _run_cli(args: List[str]) -> Any:
    """Runs ``main`` capturing stdout/stderr; returns (code, out, err)."""
    out_buf, err_buf = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out_buf), contextlib.redirect_stderr(err_buf):
        exit_code = main(args)
    return exit_code, out_buf.getvalue(), err_buf.getvalue()


class TestCliEntrypoint(unittest.TestCase):
    """End-to-end CLI runs against temporary configuration files."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.dir_path = Path(self.temp_dir.name)
        self.cfg_a = self.dir_path / "a.json"
        self.cfg_b = self.dir_path / "b.json"
        self.cfg_a.write_text('{"x": 1}', encoding="utf-8")
        self.cfg_b.write_text('{"x": 2}', encoding="utf-8")

    def test_cli_runs_each_config_and_prints_text_report(self) -> None:
        with patch(
            "main.subprocess.run",
            new=_mock_run(returncode=0, stdout="stable out\n"),
        ):
            code, out, _ = _run_cli(
                [
                    "--command",
                    "mytool --config {config}",
                    "--configs",
                    str(self.cfg_a),
                    str(self.cfg_b),
                ]
            )
        self.assertEqual(code, 0)
        self.assertIn("CONFIGURATION EXPERIMENT REPORT", out)
        self.assertIn("a.json: Exit 0", out)
        self.assertIn("[MATCH]", out)
        self.assertIn("b.json", out)

    def test_cli_json_format_emits_parseable_report(self) -> None:
        code, out, _ = _run_cli(
            [
                "--command",
                "noop",
                "--configs",
                str(self.cfg_a),
                "--format",
                "json",
            ]
        )
        self.assertEqual(code, 0)
        parsed = json.loads(out)
        self.assertEqual(parsed["baseline_config"], "a.json")

    def test_cli_output_flag_writes_report_file(self) -> None:
        target = self.dir_path / "report.md"
        code, out, _ = _run_cli(
            [
                "--command",
                "noop",
                "--configs",
                str(self.cfg_a),
                "--format",
                "markdown",
                "--output",
                str(target),
            ]
        )
        self.assertEqual(code, 0)
        self.assertIn(f"Report written to {target}", out)
        body = target.read_text(encoding="utf-8")
        self.assertIn("# Configuration Experiment Difference Report", body)

    def test_parser_requires_command_and_configs(self) -> None:
        with self.assertRaises(SystemExit):
            build_parser().parse_args(["--command", "only"])


if __name__ == "__main__":
    unittest.main()
