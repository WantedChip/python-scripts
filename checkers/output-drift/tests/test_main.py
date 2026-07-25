"""Unit tests for output-drift main.py."""

import tempfile
import unittest
from pathlib import Path

from main import (
    extract_snippets_from_markdown,
    normalize_volatile_fields,
    run_command_snippet,
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


if __name__ == "__main__":
    unittest.main()
