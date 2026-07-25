"""Markdown to HTML Converter.

Converts Markdown documents into standalone HTML pages with basic syntax support
and CSS styling template inclusion.
"""

# pylint: disable=too-many-branches,too-many-statements,too-many-locals

import argparse
import html
import re
import sys
from pathlib import Path
from typing import Dict, List, Optional

DEFAULT_CSS = """
body {
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto,
        Helvetica, Arial, sans-serif;
    line-height: 1.6;
    color: #24292e;
    max-width: 800px;
    margin: 40px auto;
    padding: 0 20px;
    background-color: #ffffff;
}
h1, h2, h3, h4, h5, h6 {
    margin-top: 24px;
    margin-bottom: 16px;
    font-weight: 600;
    line-height: 1.25;
}
h1 { font-size: 2em; border-bottom: 1px solid #eaecef; padding-bottom: 0.3em; }
h2 { font-size: 1.5em; border-bottom: 1px solid #eaecef; padding-bottom: 0.3em; }
h3 { font-size: 1.25em; }
code {
    padding: 0.2em 0.4em;
    margin: 0;
    font-size: 85%;
    background-color: rgba(27,31,35,0.05);
    border-radius: 3px;
    font-family: SFMono-Regular, Consolas, "Liberation Mono", Menlo, monospace;
}
pre {
    padding: 16px;
    overflow: auto;
    font-size: 85%;
    line-height: 1.45;
    background-color: #f68388;
    background-color: #f6f8fa;
    border-radius: 3px;
}
pre code {
    background-color: transparent;
    padding: 0;
}
blockquote {
    padding: 0 1em;
    color: #6a737d;
    border-left: 0.25em solid #dfe2e5;
    margin: 0 0 16px 0;
}
table {
    border-collapse: collapse;
    width: 100%;
    margin-bottom: 16px;
}
table th, table td {
    padding: 6px 13px;
    border: 1px solid #dfe2e5;
}
table tr:nth-child(2n) {
    background-color: #f6f8fa;
}
img {
    max-width: 100%;
}
hr {
    height: 0.25em;
    padding: 0;
    margin: 24px 0;
    background-color: #e1e4e8;
    border: 0;
}
"""

DARK_CSS = """
body {
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto,
        Helvetica, Arial, sans-serif;
    line-height: 1.6;
    color: #c9d1d9;
    max-width: 800px;
    margin: 40px auto;
    padding: 0 20px;
    background-color: #0d1117;
}
h1, h2, h3, h4, h5, h6 {
    margin-top: 24px;
    margin-bottom: 16px;
    font-weight: 600;
    color: #58a6ff;
}
h1 { font-size: 2em; border-bottom: 1px solid #30363d; padding-bottom: 0.3em; }
h2 { font-size: 1.5em; border-bottom: 1px solid #30363d; padding-bottom: 0.3em; }
code {
    padding: 0.2em 0.4em;
    font-size: 85%;
    background-color: #161b22;
    border-radius: 3px;
    font-family: monospace;
}
pre {
    padding: 16px;
    overflow: auto;
    background-color: #161b22;
    border-radius: 6px;
}
blockquote {
    padding: 0 1em;
    color: #8b949e;
    border-left: 0.25em solid #30363d;
}
table { border-collapse: collapse; width: 100%; }
table th, table td { padding: 6px 13px; border: 1px solid #30363d; }
table tr:nth-child(2n) { background-color: #161b22; }
a { color: #58a6ff; }
hr { background-color: #30363d; height: 0.25em; border: 0; }
"""

THEMES: Dict[str, str] = {
    "default": DEFAULT_CSS,
    "github": DEFAULT_CSS,
    "dark": DARK_CSS,
}


def parse_inline_markdown(text: str) -> str:
    """Parses inline Markdown markup (bold, italic, code, links, images)."""
    # Images: ![alt](url)
    text = re.sub(
        r"!\[([^\]]*)\]\(([^)]+)\)",
        r'<img src="\2" alt="\1">',
        text,
    )
    # Links: [text](url)
    text = re.sub(
        r"\[([^\]]+)\]\(([^)]+)\)",
        r'<a href="\2">\1</a>',
        text,
    )
    # Inline code: `code`
    text = re.sub(
        r"`([^`]+)`",
        lambda m: f"<code>{html.escape(m.group(1))}</code>",
        text,
    )
    # Bold: **text** or __text__
    text = re.sub(r"(\*\*|__)(.*?)\1", r"<strong>\2</strong>", text)
    # Italic: *text* or _text_
    text = re.sub(r"(\*|_)(.*?)\1", r"<em>\2</em>", text)
    # Strikethrough: ~~text~~
    text = re.sub(r"~~(.*?)~~", r"<del>\1</del>", text)

    return text


def parse_markdown(md_text: str) -> str:
    """Parses full Markdown document into HTML body content."""
    lines = md_text.splitlines()
    html_out: List[str] = []

    in_code_block = False
    code_lines: List[str] = []
    code_lang = ""

    in_list = False
    list_type = ""  # "ul" or "ol"

    in_blockquote = False
    blockquote_lines: List[str] = []

    in_table = False
    table_rows: List[str] = []

    def flush_list() -> None:
        nonlocal in_list, list_type
        if in_list:
            html_out.append(f"</{list_type}>")
            in_list = False
            list_type = ""

    def flush_blockquote() -> None:
        nonlocal in_blockquote, blockquote_lines
        if in_blockquote:
            content = parse_markdown("\n".join(blockquote_lines))
            html_out.append(f"<blockquote>\n{content}\n</blockquote>")
            in_blockquote = False
            blockquote_lines = []

    def flush_table() -> None:
        nonlocal in_table, table_rows
        if in_table and table_rows:
            html_out.append("<table>")
            for idx, row in enumerate(table_rows):
                cols = [c.strip() for c in row.strip("|").split("|")]
                if idx == 0:
                    html_out.append("  <thead>\n    <tr>")
                    for c in cols:
                        hdr = parse_inline_markdown(c)
                        html_out.append(f"      <th>{hdr}</th>")
                    html_out.append("    </tr>\n  </thead>\n  <tbody>")
                elif idx == 1 and all(
                    set(c.strip()).issubset({"-", ":", " "}) for c in cols
                ):
                    # Alignment row, skip header separator
                    continue
                else:
                    html_out.append("    <tr>")
                    for c in cols:
                        cell = parse_inline_markdown(c)
                        html_out.append(f"      <td>{cell}</td>")
                    html_out.append("    </tr>")
            html_out.append("  </tbody>\n</table>")
            in_table = False
            table_rows = []

    for line in lines:
        stripped = line.strip()

        # Fenced Code Blocks
        if stripped.startswith("```"):
            if in_code_block:
                # Close code block
                escaped_code = html.escape("\n".join(code_lines))
                lang_attr = f' class="language-{code_lang}"' if code_lang else ""
                html_out.append(f"<pre><code{lang_attr}>{escaped_code}</code></pre>")
                in_code_block = False
                code_lines = []
                code_lang = ""
            else:
                flush_list()
                flush_blockquote()
                flush_table()
                in_code_block = True
                code_lang = stripped[3:].strip()
            continue

        if in_code_block:
            code_lines.append(line)
            continue

        # Tables
        if "|" in line and (line.startswith("|") or line.endswith("|")):
            flush_list()
            flush_blockquote()
            in_table = True
            table_rows.append(line)
            continue
        if in_table:
            flush_table()

        # Blockquotes
        if stripped.startswith(">"):
            flush_list()
            flush_table()
            in_blockquote = True
            blockquote_lines.append(stripped[1:].lstrip())
            continue
        if in_blockquote:
            flush_blockquote()

        # Horizontal Rule
        if re.match(r"^(\*|\-|_){3,}$", stripped):
            flush_list()
            flush_blockquote()
            flush_table()
            html_out.append("<hr>")
            continue

        # Headings
        heading_match = re.match(r"^(#{1,6})\s+(.*)$", line)
        if heading_match:
            flush_list()
            flush_blockquote()
            flush_table()
            level = len(heading_match.group(1))
            title = parse_inline_markdown(heading_match.group(2))
            html_out.append(f"<h{level}>{title}</h{level}>")
            continue

        # Unordered Lists
        ul_match = re.match(r"^[\*\-\+]\s+(.*)$", line)
        if ul_match:
            flush_blockquote()
            flush_table()
            if not in_list or list_type != "ul":
                flush_list()
                in_list = True
                list_type = "ul"
                html_out.append("<ul>")
            item_text = parse_inline_markdown(ul_match.group(1))
            html_out.append(f"  <li>{item_text}</li>")
            continue

        # Ordered Lists
        ol_match = re.match(r"^\d+\.\s+(.*)$", line)
        if ol_match:
            flush_blockquote()
            flush_table()
            if not in_list or list_type != "ol":
                flush_list()
                in_list = True
                list_type = "ol"
                html_out.append("<ol>")
            item_text = parse_inline_markdown(ol_match.group(1))
            html_out.append(f"  <li>{item_text}</li>")
            continue

        # If not a list item, flush pending lists
        if in_list and not stripped:
            flush_list()

        # Empty lines
        if not stripped:
            flush_list()
            flush_blockquote()
            flush_table()
            continue

        # Paragraphs
        flush_list()
        flush_blockquote()
        flush_table()
        paragraph_text = parse_inline_markdown(line)
        html_out.append(f"<p>{paragraph_text}</p>")

    # Final flushes
    flush_list()
    flush_blockquote()
    flush_table()

    return "\n".join(html_out)


def convert_markdown_to_html(
    md_content: str,
    title: str = "Document",
    theme: str = "default",
) -> str:
    """Wraps parsed Markdown HTML body in a complete HTML5 template with CSS."""
    body_html = parse_markdown(md_content)
    css_content = THEMES.get(theme.lower(), DEFAULT_CSS)

    full_html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{html.escape(title)}</title>
    <style>
{css_content}
    </style>
</head>
<body>
{body_html}
</body>
</html>
"""
    return full_html


def parse_args(args: Optional[List[str]] = None) -> argparse.Namespace:
    """Parses command line arguments."""
    parser = argparse.ArgumentParser(description="Markdown to HTML Converter")
    parser.add_argument("input_file", type=str, help="Path to input Markdown file")
    parser.add_argument(
        "--output",
        "-o",
        type=str,
        default=None,
        help="Path to output HTML file (default: stdout)",
    )
    parser.add_argument(
        "--title",
        "-t",
        type=str,
        default="Converted Document",
        help="HTML page title (default: 'Converted Document')",
    )
    parser.add_argument(
        "--theme",
        choices=["default", "github", "dark"],
        default="default",
        help="CSS theme styling template (default: default)",
    )
    return parser.parse_args(args)


def main(args: Optional[List[str]] = None) -> int:
    """Main CLI entry point for markdown-to-html-converter."""
    parsed = parse_args(args)
    input_path = Path(parsed.input_file)

    if not input_path.exists():
        print(f"Error: File not found '{input_path}'", file=sys.stderr)
        return 1

    try:
        md_text = input_path.read_text(encoding="utf-8")
    except OSError as e:
        print(f"Error reading file '{input_path}': {e}", file=sys.stderr)
        return 1

    html_document = convert_markdown_to_html(
        md_content=md_text,
        title=parsed.title,
        theme=parsed.theme,
    )

    if parsed.output:
        out_path = Path(parsed.output)
        out_path.write_text(html_document, encoding="utf-8")
        msg = f"Successfully converted '{input_path}' to HTML at '{out_path}'."
        print(msg)
    else:
        print(html_document)

    return 0


if __name__ == "__main__":
    sys.exit(main())
