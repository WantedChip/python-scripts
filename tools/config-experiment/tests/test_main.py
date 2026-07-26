"""Unit tests for config-experiment tool."""

import json
import tempfile
import unittest
from pathlib import Path

from main import RunResult, compare_results, generate_report, run_single_config


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
        self.assertIn("CONFIG EXPERIMENT REPORT", text_rep)

        json_rep = generate_report(comp, fmt="json")
        parsed = json.loads(json_rep)
        self.assertEqual(parsed["baseline_config"], "cfg1.json")

        md_rep = generate_report(comp, fmt="markdown")
        self.assertIn("# Configuration Experiment Difference Report", md_rep)


if __name__ == "__main__":
    unittest.main()
