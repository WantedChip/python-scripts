"""Unit tests for example-runner tool."""

import tempfile
import unittest
from pathlib import Path

from main import CodeSnippet, execute_snippet, extract_snippets_from_markdown


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


if __name__ == "__main__":
    unittest.main()
