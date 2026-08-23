"""Unit tests for output-drift main.py."""

import contextlib
import io
import json
import subprocess  # nosec B404
import tempfile
import unittest
from pathlib import Path
from typing import Any, List
from unittest.mock import MagicMock, patch

from main import (
    CommandSnippet,
    DriftResult,
    extract_snippets_from_markdown,
    format_text_report,
    main,
    normalize_volatile_fields,
    parse_args,
    run_command_snippet,
    update_markdown_file,
)


class TestOutputDrift(unittest.TestCase):
    """Tests for output drift markdown extraction and normalization."""

    def test_normalize_volatile_fields(self) -> None:
        raw_text = (
            "Process 12345 (PID: 9876) ran on 2026-07-24T19:36:48 "
            "at 0x7ffc82a10b path: /tmp/scratch.txt in 15.2ms"
        )
        norm = normalize_volatile_fields(raw_text)
        self.assertIn("<TIMESTAMP>", norm)
        self.assertIn("PID <PID>", norm)
        self.assertIn("<ADDR>", norm)
        self.assertIn("<PATH>", norm)
        self.assertIn("<DURATION>", norm)

    def test_extract_snippets_and_run(self) -> None:
        md_content = """# Title

Here is a command example:
```bash
$ python -c "print('hello world')"
hello world
```
"""
        with tempfile.NamedTemporaryFile(
            "w", suffix=".md", delete=False, encoding="utf-8"
        ) as tmp:
            tmp.write(md_content)
            tmp_path = Path(tmp.name)

        try:
            snippets = extract_snippets_from_markdown(tmp_path)
            self.assertEqual(len(snippets), 1)
            self.assertEqual(snippets[0].command, "python -c \"print('hello world')\"")
            self.assertEqual(snippets[0].expected_output, "hello world")

            res = run_command_snippet(snippets[0])
            self.assertFalse(res.has_drift)
            self.assertEqual(res.actual_output, "hello world")
        finally:
            tmp_path.unlink()


def _make_snippet(command: str = "echo hi", expected: str = "hi") -> CommandSnippet:
    """Build a CommandSnippet anchored at a dummy markdown path."""
    return CommandSnippet(
        file_path="doc.md",
        line_number=1,
        command=command,
        expected_output=expected,
        full_block=f"$ {command}\n{expected}",
    )


@patch("main.subprocess.run")
class TestRunCommandSnippet(unittest.TestCase):
    """Tests for snippet execution against mocked subprocess boundaries."""

    def test_drift_builds_unified_diff(self, mock_run: MagicMock) -> None:
        mock_run.return_value = MagicMock(stdout="totally different\n")
        res = run_command_snippet(_make_snippet(expected="hello"))
        self.assertTrue(res.has_drift)
        self.assertIn("-hello", res.diff)
        self.assertIn("+totally different", res.diff)

    def test_timeout_marks_error_output(self, mock_run: MagicMock) -> None:
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="sleep", timeout=1)
        res = run_command_snippet(_make_snippet())
        self.assertIn("[ERROR] Command execution timed out", res.actual_output)

    def test_generic_exception_marks_error_output(self, mock_run: MagicMock) -> None:
        mock_run.side_effect = OSError("spawn failure")
        res = run_command_snippet(_make_snippet())
        self.assertIn("[ERROR] Command failed:", res.actual_output)


class TestOutputDriftExtraction(unittest.TestCase):
    """Tests for markdown snippet extraction edge cases."""

    def test_extract_missing_file_returns_empty(self) -> None:
        missing = Path("no_such_file_ever.md")
        self.assertEqual(extract_snippets_from_markdown(missing), [])

    def test_extract_multiple_commands_share_one_block(self) -> None:
        md_content = """# Doc

```sh
$ echo first
first output
$ echo second
second output
```
"""
        with tempfile.TemporaryDirectory() as tmp_dir:
            md_path = Path(tmp_dir) / "doc.md"
            md_path.write_text(md_content, encoding="utf-8")

            snippets = extract_snippets_from_markdown(md_path)
            self.assertEqual(len(snippets), 2)
            self.assertEqual(snippets[0].command, "echo first")
            self.assertEqual(snippets[0].expected_output, "first output")
            self.assertEqual(snippets[1].command, "echo second")
            self.assertEqual(snippets[1].expected_output, "second output")


class TestOutputDriftReporting(unittest.TestCase):
    """Tests for report formatting and markdown auto-update."""

    def test_format_text_report_all_match(self) -> None:
        result = DriftResult(
            file_path="doc.md",
            line_number=3,
            command="echo hi",
            expected_output="hi",
            actual_output="hi",
            normalized_expected="hi",
            normalized_actual="hi",
            has_drift=False,
            diff="",
        )
        report = format_text_report([result])
        self.assertIn("All 1 documentation command outputs match", report)

    def test_format_text_report_lists_drifts(self) -> None:
        result = DriftResult(
            file_path="doc.md",
            line_number=3,
            command="echo hi",
            expected_output="hi",
            actual_output="bye",
            normalized_expected="hi",
            normalized_actual="bye",
            has_drift=True,
            diff="-hi\n+bye",
        )
        report = format_text_report([result])
        self.assertIn("[DRIFT DETECTED] doc.md:3", report)
        self.assertIn("-hi", report)
        self.assertIn("+bye", report)

    def test_update_markdown_replaces_drifted_output_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            md_path = Path(tmp_dir) / "doc.md"
            md_path.write_text(
                "```bash\n$ echo hi\nstale output\n```\n", encoding="utf-8"
            )
            drifted = DriftResult(
                file_path=str(md_path),
                line_number=2,
                command="echo hi",
                expected_output="stale output",
                actual_output="fresh output",
                normalized_expected="stale output",
                normalized_actual="fresh output",
                has_drift=True,
                diff="",
            )
            errored = DriftResult(
                file_path=str(md_path),
                line_number=5,
                command="boom",
                expected_output="old",
                actual_output="[ERROR] Command failed: x",
                normalized_expected="old",
                normalized_actual="[ERROR]",
                has_drift=True,
                diff="",
            )
            update_markdown_file(md_path, [drifted, errored])

            content = md_path.read_text(encoding="utf-8")
            self.assertIn("fresh output", content)
            self.assertNotIn("stale output", content)
            # Error results must never be written into documentation.
            self.assertNotIn("[ERROR]", content)


class TestOutputDriftCli(unittest.TestCase):
    """End-to-end CLI tests with mocked subprocess execution."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def _write_md(self, name: str, content: str) -> Path:
        path = self.root / name
        path.write_text(content, encoding="utf-8")
        return path

    def test_main_missing_path_returns_error(self) -> None:
        ret = main([str(self.root / "missing_dir")])
        self.assertEqual(ret, 1)

    def test_main_without_snippets_exits_zero(self) -> None:
        md_path = self._write_md("plain.md", "# Just prose, no commands.\n")
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            ret = main([str(md_path)])
        self.assertEqual(ret, 0)
        self.assertIn("No command snippets", buf.getvalue())

    @patch("main.subprocess.run")
    def test_main_matching_output_exits_zero(self, mock_run: MagicMock) -> None:
        mock_run.return_value = MagicMock(stdout="stable output\n")
        md_path = self._write_md("ok.md", "```bash\n$ emit\nstable output\n```\n")
        ret = main([str(md_path)])
        self.assertEqual(ret, 0)

    @patch("main.subprocess.run")
    def test_main_drifted_output_exits_one_with_text_report(
        self, mock_run: MagicMock
    ) -> None:
        mock_run.return_value = MagicMock(stdout="actual output\n")
        md_path = self._write_md("bad.md", "```bash\n$ emit\nexpected output\n```\n")
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            ret = main([str(md_path)])
        self.assertEqual(ret, 1)
        self.assertIn("[DRIFT DETECTED]", buf.getvalue())

    @patch("main.subprocess.run")
    def test_main_json_format_prints_results(self, mock_run: MagicMock) -> None:
        mock_run.return_value = MagicMock(stdout="actual\n")
        md_path = self._write_md("j.md", "```bash\n$ emit\nexpected\n```\n")
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            ret = main(["--format", "json", str(md_path)])
        self.assertEqual(ret, 1)
        payload: List[Any] = json.loads(buf.getvalue())
        self.assertEqual(payload[0]["command"], "emit")
        self.assertTrue(payload[0]["has_drift"])

    @patch("main.subprocess.run")
    def test_main_update_flag_rewrites_documentation(self, mock_run: MagicMock) -> None:
        mock_run.return_value = MagicMock(stdout="correct output\n")
        md_path = self._write_md("up.md", "```bash\n$ emit\nwrong output\n```\n")
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            ret = main(["--update", str(md_path)])
        self.assertEqual(ret, 1)
        self.assertIn("Updated Markdown documentation files", buf.getvalue())
        self.assertIn("correct output", md_path.read_text(encoding="utf-8"))

    @patch("main.subprocess.run")
    def test_main_scans_directory_recursively(self, mock_run: MagicMock) -> None:
        mock_run.return_value = MagicMock(stdout="stable output\n")
        nested = self.root / "docs"
        nested.mkdir()
        (nested / "a.md").write_text(
            "```bash\n$ emit\nstable output\n```\n", encoding="utf-8"
        )
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            ret = main([str(self.root)])
        self.assertEqual(ret, 0)
        self.assertIn("All 1 documentation command outputs match", buf.getvalue())

    def test_cli_arg_parsing_defaults(self) -> None:
        parsed = parse_args([])
        self.assertEqual(parsed.path, ".")
        self.assertFalse(parsed.update)
        self.assertEqual(parsed.timeout, 10)
        self.assertEqual(parsed.format, "text")


if __name__ == "__main__":
    unittest.main()
