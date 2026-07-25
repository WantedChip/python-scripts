import tempfile
import unittest
from pathlib import Path

from main import ProvenanceTracker


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


if __name__ == "__main__":
    unittest.main()
