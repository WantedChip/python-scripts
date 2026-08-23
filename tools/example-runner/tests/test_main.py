"""Unit tests for example-runner tool."""

import io
import subprocess
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from types import SimpleNamespace
from typing import Optional
from unittest.mock import MagicMock, patch

from main import (
    CodeSnippet,
    ExecutionResult,
    build_parser,
    execute_snippet,
    extract_snippets_from_markdown,
    main,
)


class TestExampleRunner(unittest.TestCase):
    """Test suite for example-runner functionality."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_extract_snippets_from_markdown(self) -> None:
        md_file = self.root / "test.md"
        content = (
            "# Documentation Sample\n\n"
            "Here is python:\n"
            "```python\n"
            "print('Hello World')\n"
            "# Output: Hello World\n"
            "```\n\n"
            "Here is bash:\n"
            "```bash\n"
            "echo hello\n"
            "```\n"
        )
        md_file.write_text(content, encoding="utf-8")

        snippets = extract_snippets_from_markdown(md_file)
        self.assertEqual(len(snippets), 2)
        self.assertEqual(snippets[0].language, "python")
        self.assertEqual(snippets[0].expected_output, "Hello World")
        self.assertEqual(snippets[1].language, "bash")

    def test_execute_python_snippet_success(self) -> None:
        snip = CodeSnippet(
            file_path=Path("doc.md"),
            line_number=5,
            language="python",
            code="x = 10 + 5\nprint(f'Result: {x}')\n# Expected: Result: 15",
            expected_output="Result: 15",
        )
        res = execute_snippet(snip)
        self.assertTrue(res.passed)
        self.assertIn("Result: 15", res.stdout)

    def test_execute_python_snippet_failure(self) -> None:
        snip = CodeSnippet(
            file_path=Path("doc.md"),
            line_number=10,
            language="python",
            code="raise ValueError('Syntax or runtime error')",
        )
        res = execute_snippet(snip)
        self.assertFalse(res.passed)
        self.assertIn("ValueError", res.stderr)


def _snippet(language: str, code: str, expected: Optional[str] = None) -> CodeSnippet:
    """Build a snippet bound to a placeholder document path."""
    return CodeSnippet(
        file_path=Path("doc.md"),
        line_number=1,
        language=language,
        code=code,
        expected_output=expected,
    )


class TestExecuteSnippetEdgeCases(unittest.TestCase):
    """Tests for shell command building, output mismatch, and error paths."""

    def test_extract_missing_file_returns_empty(self) -> None:
        """A nonexistent markdown file yields no snippets."""
        self.assertEqual(extract_snippets_from_markdown(Path("Z:/no/such.md")), [])

    @patch("main.subprocess.run")
    def test_bash_snippet_uses_shell_command(self, mock_run: MagicMock) -> None:
        """Bash snippets run through a shell command string on the host OS."""
        mock_run.return_value = SimpleNamespace(
            returncode=0, stdout="hello\n", stderr=""
        )
        res = execute_snippet(_snippet("bash", "echo hello"))

        self.assertTrue(res.passed)
        args, kwargs = mock_run.call_args
        cmd = args[0]
        self.assertIsInstance(cmd, str)
        self.assertIn("example.sh", cmd)
        self.assertTrue(kwargs["shell"])

    def test_expected_output_mismatch_fails(self) -> None:
        """A snippet whose stdout lacks the expected text is marked failed."""
        snip = _snippet("python", "print('actual')", expected="expected-text")
        res = execute_snippet(snip)

        self.assertFalse(res.passed)
        self.assertIn("Expected 'expected-text'", res.message)
        self.assertIn("actual", res.stdout)

    def test_expected_output_matched_in_stderr(self) -> None:
        """Expected text found on stderr still counts as a pass."""
        snip = _snippet(
            "python",
            "import sys; print('hint', file=sys.stderr)",
            expected="hint",
        )
        res = execute_snippet(snip)
        self.assertTrue(res.passed)
        self.assertIn("(Expected output matched)", res.message)

    @patch(
        "main.subprocess.run",
        side_effect=subprocess.TimeoutExpired(cmd="x", timeout=0.01),
    )
    def test_timeout_returns_failed_result(self, _mock_run: MagicMock) -> None:
        """A TimeoutExpired from subprocess becomes a failed result."""
        res = execute_snippet(_snippet("python", "pass"), timeout=0.01)
        self.assertFalse(res.passed)
        self.assertEqual(res.exit_code, -1)
        self.assertIn("timed out", res.message)

    @patch("main.subprocess.run", side_effect=OSError("spawn failed"))
    def test_os_error_returns_failed_result(self, _mock_run: MagicMock) -> None:
        """An OSError from subprocess becomes a failed result with message."""
        res = execute_snippet(_snippet("python", "pass"))
        self.assertFalse(res.passed)
        self.assertEqual(res.exit_code, -1)
        self.assertIn("Execution error: spawn failed", res.message)


class TestMainCLI(unittest.TestCase):
    """End-to-end CLI tests over temporary markdown documents."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def _write_doc(self, name: str, body: str) -> Path:
        """Write a markdown document into the temp root and return its path."""
        doc = self.root / name
        doc.write_text(body, encoding="utf-8")
        return doc

    def test_build_parser_defaults_and_timeout(self) -> None:
        """The parser accepts multiple paths and an optional timeout."""
        parsed = build_parser().parse_args(["a.md", "b.md", "--timeout", "2.5"])
        self.assertEqual(parsed.paths, ["a.md", "b.md"])
        self.assertEqual(parsed.timeout, 2.5)

    def test_main_no_markdown_files(self) -> None:
        """Scanning an empty directory reports no files and exits 0."""
        empty_dir = self.root / "empty"
        empty_dir.mkdir()

        buf = io.StringIO()
        with redirect_stdout(buf):
            code = main([str(empty_dir)])
        self.assertEqual(code, 0)
        self.assertIn("No Markdown files found.", buf.getvalue())

    def test_main_directory_scan_all_pass(self) -> None:
        """Directory scanning collects nested snippets that all pass."""
        sub = self.root / "docs"
        sub.mkdir()
        (sub / "guide.md").write_text(
            "# Guide\n```python\nprint('ok')\n```\n", encoding="utf-8"
        )

        code = main([str(self.root)])
        self.assertEqual(code, 0)

    def test_main_failure_reports_and_exits_nonzero(self) -> None:
        """Failing snippets are listed with stderr and force exit code 1."""
        self._write_doc(
            "broken.md",
            "```python\nraise RuntimeError('boom')\n```\n",
        )

        code = main([str(self.root)])
        self.assertEqual(code, 1)

    def test_main_skips_non_markdown_files(self) -> None:
        """Non-markdown path arguments are ignored entirely."""
        txt = self.root / "notes.txt"
        txt.write_text("```python\nprint('never run')\n```\n", encoding="utf-8")

        with patch("main.execute_snippet") as mock_exec:
            mock_exec.return_value = ExecutionResult(
                snippet=_snippet("python", "pass"),
                passed=True,
                exit_code=0,
                stdout="",
                stderr="",
                message="Exit code 0",
            )
            code = main([str(txt)])
        self.assertEqual(code, 0)
        mock_exec.assert_not_called()


if __name__ == "__main__":
    unittest.main()
