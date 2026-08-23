"""Unit tests for Agent Boundary Tool."""

import contextlib
import io
import os
import tempfile
import unittest
from pathlib import Path
from typing import List, Tuple

from main import ContributionReport, ProvenanceTracker, main


def _run_cli(args: List[str]) -> Tuple[int, str]:
    """Runs the CLI with redirected stdout; returns (exit_code, output)."""
    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        exit_code = main(args)
    return exit_code, buffer.getvalue()


class TestAgentBoundary(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.ledger_file = Path(self.temp_dir.name) / "ledger.json"

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_record_human_and_agent_edits(self):
        tracker = ProvenanceTracker(ledger_file=self.ledger_file)

        # Human creates initial file content
        tracker.record_edit_session(
            file_path="app.py",
            new_content="line 1\nline 2\n",
            author_type="HUMAN",
            author_name="Alice",
        )

        rep1 = tracker.generate_report()
        self.assertEqual(rep1.human_lines, 2)
        self.assertEqual(rep1.agent_lines, 0)

        # Agent appends line 3
        tracker.record_edit_session(
            file_path="app.py",
            new_content="line 1\nline 2\nline 3\n",
            author_type="AGENT",
            author_name="Bot",
        )

        rep2 = tracker.generate_report()
        self.assertEqual(rep2.human_lines, 2)
        self.assertEqual(rep2.agent_lines, 1)
        self.assertEqual(rep2.overwritten_human_lines, 0)

    def test_overwritten_human_edit_detection(self):
        tracker = ProvenanceTracker(ledger_file=self.ledger_file)

        tracker.record_edit_session(
            file_path="app.py",
            new_content="human code line\n",
            author_type="HUMAN",
            author_name="Bob",
        )

        # Agent overwrites human code line
        tracker.record_edit_session(
            file_path="app.py",
            new_content="agent code line\n",
            author_type="AGENT",
            author_name="Bot",
        )

        rep = tracker.generate_report()
        self.assertEqual(rep.overwritten_human_lines, 1)


class TestLedgerPersistence(unittest.TestCase):
    """Tests for ledger load/save round-trips and corrupt input handling."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.ledger_file = Path(self.temp_dir.name) / "ledger.json"

    def test_missing_ledger_file_loads_empty(self) -> None:
        tracker = ProvenanceTracker(ledger_file=self.ledger_file)
        self.assertEqual(tracker.ledger_data, {})

    def test_corrupt_ledger_json_loads_empty_without_raising(self) -> None:
        self.ledger_file.write_text("{broken json", encoding="utf-8")
        tracker = ProvenanceTracker(ledger_file=self.ledger_file)
        self.assertEqual(tracker.ledger_data, {})

    def test_save_and_reload_roundtrip_preserves_provenance(self) -> None:
        tracker = ProvenanceTracker(ledger_file=self.ledger_file)
        tracker.record_edit_session(
            file_path="src/app.py",
            new_content="keep\nnew\n",
            author_type="HUMAN",
            author_name="Alice",
        )
        reloaded = ProvenanceTracker(ledger_file=self.ledger_file)
        ledger = reloaded.ledger_data["src/app.py"]
        self.assertEqual([lp.content for lp in ledger.lines], ["keep", "new"])
        self.assertEqual(ledger.lines[0].author_type, "HUMAN")
        self.assertEqual(ledger.lines[0].author_name, "Alice")


class TestRecordEditSessionRules(unittest.TestCase):
    """Behavioural rules for recording edit sessions."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.ledger_file = Path(self.temp_dir.name) / "ledger.json"

    def _tracker(self) -> ProvenanceTracker:
        return ProvenanceTracker(ledger_file=self.ledger_file)

    def test_lowercase_author_type_is_normalised(self) -> None:
        tracker = self._tracker()
        tracker.record_edit_session(
            file_path="a.py",
            new_content="x\n",
            author_type="human",
            author_name="Ana",
        )
        report = tracker.generate_report()
        self.assertEqual(report.human_lines, 1)

    def test_invalid_author_type_raises_value_error(self) -> None:
        tracker = self._tracker()
        with self.assertRaises(ValueError):
            tracker.record_edit_session(
                file_path="a.py",
                new_content="x\n",
                author_type="ROBOT",
                author_name="R2",
            )

    def test_agent_outside_scope_appends_violation(self) -> None:
        tracker = self._tracker()
        f_ledger = tracker.record_edit_session(
            file_path="docs/readme.md",
            new_content="hi\n",
            author_type="AGENT",
            author_name="Bot",
            allowed_scope_patterns=["src/*"],
        )
        self.assertEqual(len(f_ledger.scope_violations), 1)
        self.assertIn("outside permitted scope ['src/*']", f_ledger.scope_violations[0])
        self.assertIn("docs/readme.md", f_ledger.scope_violations[0])

    def test_agent_filename_pattern_match_is_in_scope(self) -> None:
        tracker = self._tracker()
        f_ledger = tracker.record_edit_session(
            file_path="deep/nested/app.py",
            new_content="code\n",
            author_type="AGENT",
            author_name="Bot",
            allowed_scope_patterns=["*.py"],
        )
        self.assertEqual(f_ledger.scope_violations, [])

    def test_scope_rules_not_enforced_for_human_edits(self) -> None:
        tracker = self._tracker()
        f_ledger = tracker.record_edit_session(
            file_path="secrets.env",
            new_content="KEY=1\n",
            author_type="HUMAN",
            author_name="Admin",
            allowed_scope_patterns=["src/*"],
        )
        self.assertEqual(f_ledger.scope_violations, [])

    def test_agent_deleting_human_lines_counts_as_overwritten(self) -> None:
        tracker = self._tracker()
        tracker.record_edit_session(
            file_path="a.py",
            new_content="one\ntwo\nthree\n",
            author_type="HUMAN",
            author_name="Ola",
        )
        tracker.record_edit_session(
            file_path="a.py",
            new_content="two\nthree\n",
            author_type="AGENT",
            author_name="Bot",
        )
        report = tracker.generate_report()
        self.assertEqual(report.overwritten_human_lines, 1)
        self.assertEqual(report.total_lines, 2)


class TestContributionReportMath(unittest.TestCase):
    """Percentage computations on the summary dataclass."""

    def test_percentages_split_evenly_for_mixed_authors(self) -> None:
        report = ContributionReport(total_lines=8, human_lines=6, agent_lines=2)
        self.assertEqual(report.human_percentage, 75.0)
        self.assertEqual(report.agent_percentage, 25.0)

    def test_empty_report_reports_zero_percentages(self) -> None:
        empty = ContributionReport()
        self.assertEqual(empty.total_lines, 0)
        self.assertEqual(empty.human_percentage, 0.0)
        self.assertEqual(empty.agent_percentage, 0.0)


class TestCliCommands(unittest.TestCase):
    """End-to-end CLI runs against a temporary working directory."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.prev_cwd = os.getcwd()
        os.chdir(self.temp_dir.name)
        self.addCleanup(os.chdir, self.prev_cwd)

    def _write_target(self) -> None:
        Path("app.py").write_text("def main():\n    pass\n", encoding="utf-8")

    def test_no_command_prints_help_and_returns_one(self) -> None:
        code, out = _run_cli([])
        self.assertEqual(code, 1)
        self.assertIn("usage:", out)

    def test_record_missing_file_returns_error(self) -> None:
        code, out = _run_cli(
            [
                "record",
                "--file",
                "ghost.py",
                "--author-type",
                "AGENT",
                "--author-name",
                "Bot",
                "--ledger",
                "ledger.json",
            ]
        )
        self.assertEqual(code, 1)
        self.assertIn("does not exist", out)

    def test_record_then_report_flow_tracks_contributions(self) -> None:
        self._write_target()
        code, out = _run_cli(
            [
                "record",
                "--file",
                "app.py",
                "--author-type",
                "HUMAN",
                "--author-name",
                "Dana",
                "--ledger",
                "ledger.json",
            ]
        )
        self.assertEqual(code, 0)
        self.assertIn("Recorded edit session for 'app.py' by HUMAN (Dana).", out)
        self.assertTrue(Path("ledger.json").exists())

        _, out = _run_cli(["report", "--ledger", "ledger.json"])
        self.assertIn("Total Lines Tracked:     2", out)
        self.assertIn("Human Originated Lines:  2 (100.0%)", out)
        self.assertIn("Agent Originated Lines:  0 (0.0%)", out)

    def test_record_agent_scope_violation_warns_on_stdout(self) -> None:
        self._write_target()
        code, out = _run_cli(
            [
                "record",
                "--file",
                "app.py",
                "--author-type",
                "AGENT",
                "--author-name",
                "Bot",
                "--scope",
                "src/*",
                "--ledger",
                "ledger.json",
            ]
        )
        self.assertEqual(code, 0)
        self.assertIn("[WARNING] Scope Violation:", out)

        _, report_out = _run_cli(["report", "--ledger", "ledger.json"])
        self.assertIn("[ALERTS] Scope Violations (1):", report_out)


if __name__ == "__main__":
    unittest.main()
