"""Unit tests for Markdown to HTML Converter."""

import unittest

from main import (
    convert_markdown_to_html,
    parse_args,
    parse_inline_markdown,
    parse_markdown,
)


class TestMarkdownToHtmlConverter(unittest.TestCase):
    """Test suite for Markdown to HTML converter."""

    def test_inline_markdown_parsing(self) -> None:
        md_inline = (
            "This is **bold**, *italic*, `code`, and a [link](https://example.com)."
        )
        parsed = parse_inline_markdown(md_inline)

        self.assertIn("<strong>bold</strong>", parsed)
        self.assertIn("<em>italic</em>", parsed)
        self.assertIn("<code>code</code>", parsed)
        self.assertIn('<a href="https://example.com">link</a>', parsed)

    def test_headings_and_lists(self) -> None:
        md_content = """# Heading 1
## Heading 2

- Item 1
- Item 2
"""
        html_out = parse_markdown(md_content)

        self.assertIn("<h1>Heading 1</h1>", html_out)
        self.assertIn("<h2>Heading 2</h2>", html_out)
        self.assertIn("<ul>", html_out)
        self.assertIn("<li>Item 1</li>", html_out)
        self.assertIn("</ul>", html_out)

    def test_code_block_and_blockquote(self) -> None:
        md_content = """```python
def foo():
    return 42
```

> This is a quote
"""
        html_out = parse_markdown(md_content)

        self.assertIn('<pre><code class="language-python">def foo():', html_out)
        self.assertIn("<blockquote>", html_out)
        self.assertIn("<p>This is a quote</p>", html_out)

    def test_table_parsing(self) -> None:
        md_table = """| Header 1 | Header 2 |
| --- | --- |
| Val 1 | Val 2 |"""
        html_out = parse_markdown(md_table)

        self.assertIn("<table>", html_out)
        self.assertIn("<th>Header 1</th>", html_out)
        self.assertIn("<td>Val 1</td>", html_out)

    def test_full_document_template(self) -> None:
        md_content = "# Title\nParagraph text."
        html_doc = convert_markdown_to_html(md_content, title="Test Doc", theme="dark")

        self.assertIn("<!DOCTYPE html>", html_doc)
        self.assertIn("<title>Test Doc</title>", html_doc)
        self.assertIn("background-color: #0d1117;", html_doc)  # dark theme css
        self.assertIn("<h1>Title</h1>", html_doc)

    def test_parse_args(self) -> None:
        raw_args = [
            "doc.md",
            "-o",
            "doc.html",
            "--theme",
            "dark",
            "--title",
            "My Page",
        ]
        args = parse_args(raw_args)
        self.assertEqual(args.input_file, "doc.md")
        self.assertEqual(args.output, "doc.html")
        self.assertEqual(args.theme, "dark")
        self.assertEqual(args.title, "My Page")


if __name__ == "__main__":
    unittest.main()
