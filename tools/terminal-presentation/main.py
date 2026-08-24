"""Terminal Presentation Tool.

Parses Markdown files into slides, renders clean ANSI terminal formatting with syntax
highlighting, supports live code snippet execution, and provides keyboard navigation.
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess  # nosec B404
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

# pylint: disable=too-many-branches,too-many-statements
# pylint: disable=too-many-locals,too-many-arguments,too-many-positional-arguments
# pylint: disable=too-many-instance-attributes,too-few-public-methods
# pylint: disable=broad-exception-caught,import-outside-toplevel
# pylint: disable=no-else-return,line-too-long,unused-argument,import-error


# ANSI Color Constants
RESET = "\033[0m"
BOLD = "\033[1m"
DIM = "\033[2m"
ITALIC = "\033[3m"
UNDERLINE = "\033[4m"

COLOR_HEADER = "\033[38;5;39m"  # Bright cyan
COLOR_SUBHEADER = "\033[38;5;75m"  # Medium cyan
COLOR_TEXT = "\033[38;5;252m"  # Off-white
COLOR_CODE = "\033[38;5;215m"  # Light orange/peach
COLOR_KEYWORD = "\033[38;5;204m"  # Pink/red
COLOR_STRING = "\033[38;5;114m"  # Light green
COLOR_COMMENT = "\033[38;5;243m"  # Dark gray
COLOR_BORDER = "\033[38;5;240m"  # Dark gray box border
COLOR_ACCENT = "\033[38;5;220m"  # Bright yellow
COLOR_EXEC_OUT = "\033[38;5;147m"  # Light violet


@dataclass
class CodeBlock:
    """Represents a code snippet embedded in a slide."""

    language: str
    code: str
    executable: bool = False


@dataclass
class Slide:
    """Represents a single presentation slide."""

    title: str
    raw_content: str
    code_blocks: List[CodeBlock] = field(default_factory=list)


class SlideDeck:
    """Container and parser for presentation slides."""

    def __init__(self, slides: Optional[List[Slide]] = None):
        self.slides: List[Slide] = slides or []

    @classmethod
    def from_markdown(cls, md_text: str) -> SlideDeck:
        """Parse markdown text into slides separated by '---' or '# ' headers."""
        deck = cls()
        sections = re.split(r"\n\s*---\s*\n", md_text)
        raw_slides: List[str] = []

        for sec in sections:
            h1_splits = re.split(r"(?=\n#\s+)", sec)
            for chunk in h1_splits:
                cleaned = chunk.strip()
                if cleaned:
                    raw_slides.append(cleaned)

        for raw in raw_slides:
            slide = cls._parse_single_slide(raw)
            deck.slides.append(slide)

        if not deck.slides:
            deck.slides.append(
                Slide(
                    title="Empty Deck",
                    raw_content="No slide content found.",
                )
            )

        return deck

    @staticmethod
    def _parse_single_slide(raw_text: str) -> Slide:
        title = "Untitled Slide"
        lines = raw_text.splitlines()

        for line in lines:
            if line.startswith("#"):
                title = line.lstrip("#").strip()
                break

        code_blocks: List[CodeBlock] = []
        code_pattern = re.compile(r"```(\w*)\n(.*?)```", re.DOTALL)
        for match in code_pattern.finditer(raw_text):
            lang = match.group(1).lower() or "text"
            code = match.group(2).strip()
            exec_langs = ("bash", "sh", "exec", "python", "py", "exec-py")
            executable = lang in exec_langs
            code_blocks.append(
                CodeBlock(language=lang, code=code, executable=executable)
            )

        return Slide(title=title, raw_content=raw_text, code_blocks=code_blocks)


def highlight_code(code: str, lang: str) -> str:
    """Apply basic ANSI syntax highlighting to code snippet."""
    lines = code.splitlines()
    highlighted_lines = []

    keywords = {
        "def",
        "class",
        "import",
        "from",
        "return",
        "if",
        "else",
        "elif",
        "for",
        "while",
        "try",
        "except",
        "with",
        "as",
        "echo",
        "cd",
        "ls",
        "cat",
        "grep",
        "sudo",
        "apt",
        "python",
        "pip",
    }

    for line in lines:
        if line.strip().startswith("#") or line.strip().startswith("//"):
            highlighted_lines.append(f"{COLOR_COMMENT}{line}{RESET}")
            continue

        words = line.split(" ")
        colored_words = []
        for word in words:
            clean_word = re.sub(r"\W", "", word)
            if clean_word in keywords:
                colored = word.replace(
                    clean_word, f"{COLOR_KEYWORD}{clean_word}{RESET}"
                )
                colored_words.append(colored)
            elif (
                word.startswith('"')
                or word.startswith("'")
                or word.endswith('"')
                or word.endswith("'")
            ):
                colored_words.append(f"{COLOR_STRING}{word}{RESET}")
            else:
                colored_words.append(f"{COLOR_CODE}{word}{RESET}")
        highlighted_lines.append(" ".join(colored_words))

    return "\n".join(highlighted_lines)


def execute_snippet(block: CodeBlock, timeout: int = 5) -> str:
    """Execute code snippet live and capture stdout/stderr."""
    lang = block.language.lower()
    code = block.code

    try:
        if lang in ("python", "py", "exec-py"):
            res = subprocess.run(  # nosec
                [sys.executable, "-c", code],
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False,
            )
        elif lang in ("bash", "sh", "exec"):
            shell_cmd = (
                ["bash", "-c", code] if os.name != "nt" else ["cmd.exe", "/c", code]
            )
            res = subprocess.run(  # nosec
                shell_cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False,
            )
        else:
            return f"[Execution unsupported for language '{lang}']"

        output = res.stdout
        if res.stderr:
            output += f"\n[stderr]: {res.stderr}"
        if res.returncode != 0:
            output += f"\n[exit status: {res.returncode}]"
        return output.strip() or "[No Output]"

    except subprocess.TimeoutExpired:
        return f"[Execution Timed Out ({timeout}s)]"
    except Exception as e:
        return f"[Execution Error: {e}]"


def render_slide(
    slide: Slide,
    current_index: int,
    total_slides: int,
    width: int = 80,
    run_code: bool = False,
) -> str:
    """Format and frame a single slide into ANSI terminal string."""
    term_width = min(width, shutil.get_terminal_size((80, 24)).columns)
    inner_width = term_width - 4

    top_b = f"{COLOR_BORDER}╭" + "─" * (term_width - 2) + f"╮{RESET}"
    bot_b = f"{COLOR_BORDER}╰" + "─" * (term_width - 2) + f"╯{RESET}"

    # Header title
    title_str = f" {slide.title} "
    title_centered = title_str.center(inner_width, "─")
    header_line = (
        f"{COLOR_BORDER}│{RESET}"
        f" {COLOR_HEADER}{BOLD}{title_centered}{RESET} {COLOR_BORDER}│{RESET}"
    )
    sep_line = f"{COLOR_BORDER}├" + "─" * (term_width - 2) + f"┤{RESET}"

    lines = [top_b, header_line, sep_line]

    # Process content lines
    content_lines = slide.raw_content.splitlines()
    in_code_block = False
    current_code_lines: List[str] = []
    current_lang = ""

    for line in content_lines:
        if line.startswith("#"):
            if line.lstrip("#").strip() == slide.title:
                continue
            hdr_text = line.lstrip("#").strip()
            sub_hdr = f"{COLOR_SUBHEADER}{BOLD}# {hdr_text}{RESET}"
            line_str = f"{COLOR_BORDER}│{RESET} {sub_hdr}".ljust(term_width + 10)
            lines.append(f"{line_str}{COLOR_BORDER}│{RESET}")
            continue

        if line.startswith("```"):
            if not in_code_block:
                in_code_block = True
                current_lang = line.replace("```", "").strip() or "text"
                current_code_lines = []
            else:
                in_code_block = False
                raw_code = "\n".join(current_code_lines)
                highlighted = highlight_code(raw_code, current_lang)

                code_top = (
                    f"{COLOR_BORDER}│{RESET} {COLOR_BORDER}┌─ [code:"
                    f" {current_lang}] "
                    + "─" * (inner_width - len(current_lang) - 12)
                    + f"┐{RESET}"
                )
                lines.append(code_top)
                for cl in highlighted.splitlines():
                    cl_str = (
                        f"{COLOR_BORDER}│{RESET} {COLOR_BORDER}│{RESET} {cl}".ljust(
                            term_width + 15
                        )
                    )
                    lines.append(f"{cl_str}{COLOR_BORDER}│{RESET}")
                code_bot = (
                    f"{COLOR_BORDER}│{RESET} {COLOR_BORDER}└"
                    + "─" * (inner_width - 2)
                    + f"┘{RESET}"
                )
                lines.append(code_bot)

                if run_code:
                    block = CodeBlock(
                        language=current_lang,
                        code=raw_code,
                        executable=True,
                    )
                    exec_res = execute_snippet(block)
                    lines.append(
                        f"{COLOR_BORDER}│{RESET} {COLOR_ACCENT}▶ Live"
                        f" Output:{RESET}"
                    )
                    for el in exec_res.splitlines():
                        el_str = (
                            f"{COLOR_BORDER}│{RESET}  "
                            f" {COLOR_EXEC_OUT}{el}{RESET}".ljust(term_width + 15)
                        )
                        lines.append(f"{el_str}{COLOR_BORDER}│{RESET}")
            continue

        if in_code_block:
            current_code_lines.append(line)
            continue

        # Bullet points
        if line.strip().startswith("- ") or line.strip().startswith("* "):
            bullet_text = line.strip()[2:]
            rendered = f"  {COLOR_ACCENT}•{RESET} {COLOR_TEXT}{bullet_text}{RESET}"
            r_str = f"{COLOR_BORDER}│{RESET} {rendered}".ljust(term_width + 15)
            lines.append(f"{r_str}{COLOR_BORDER}│{RESET}")
        else:
            txt_str = f"{COLOR_BORDER}│{RESET} {COLOR_TEXT}{line}{RESET}".ljust(
                term_width + 12
            )
            lines.append(f"{txt_str}{COLOR_BORDER}│{RESET}")

    # Footer navigation bar
    nav_str = (
        f" Slide {current_index + 1}/{total_slides} | [n]ext [p]rev [e]xec" " [q]uit "
    )
    nav_formatted = nav_str.rjust(inner_width)
    footer_line = (
        f"{COLOR_BORDER}│{RESET} {DIM}{nav_formatted}{RESET}" f" {COLOR_BORDER}│{RESET}"
    )

    lines.append(f"{COLOR_BORDER}├" + "─" * (term_width - 2) + f"┤{RESET}")
    lines.append(footer_line)
    lines.append(bot_b)

    return "\n".join(lines)


def get_key_press() -> str:
    """Read a single keypress cross-platform."""
    # sys.platform (not os.name) so type checkers narrow each backend to
    # the platform that actually ships it.
    if sys.platform == "win32":
        import msvcrt

        ch = msvcrt.getch()
        if ch in (b"\x00", b"\xe0"):
            ch = msvcrt.getch()
        return ch.decode("utf-8", errors="ignore").lower()
    else:
        import termios
        import tty

        fd = sys.stdin.fileno()
        old_settings = termios.tcgetattr(fd)
        try:
            tty.setraw(sys.stdin.fileno())
            ch_str: str = sys.stdin.read(1)
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
        return ch_str.lower()


def run_interactive_presentation(deck: SlideDeck, auto_run_code: bool = False) -> None:
    """Main interactive slideshow loop."""
    current_idx = 0
    total = len(deck.slides)
    run_code_flags = [auto_run_code] * total

    while True:
        os.system("cls" if os.name == "nt" else "clear")  # nosec
        slide = deck.slides[current_idx]
        output = render_slide(
            slide,
            current_index=current_idx,
            total_slides=total,
            run_code=run_code_flags[current_idx],
        )
        print(output)

        key = get_key_press()
        if key in ("q", "\x1b"):
            break
        if key in ("n", " ", "\r"):
            if current_idx < total - 1:
                current_idx += 1
        elif key in ("p", "b"):
            if current_idx > 0:
                current_idx -= 1
        elif key in ("e", "x"):
            run_code_flags[current_idx] = not run_code_flags[current_idx]


def build_parser() -> argparse.ArgumentParser:
    """Build CLI parser."""
    parser = argparse.ArgumentParser(description="Terminal Presentation Viewer.")
    parser.add_argument("file", type=str, help="Path to markdown presentation file.")
    parser.add_argument("--slide", type=int, default=1, help="Slide number to display.")
    parser.add_argument(
        "--run-code", action="store_true", help="Auto-run code snippets live."
    )
    parser.add_argument(
        "--non-interactive",
        action="store_true",
        help="Render requested slide non-interactively and exit.",
    )
    parser.add_argument(
        "--export-text",
        type=str,
        help="Export all rendered slides to text file.",
    )
    return parser


def main(args: Optional[List[str]] = None) -> int:
    """CLI entrypoint."""
    parser = build_parser()
    parsed = parser.parse_args(args)

    md_path = Path(parsed.file)
    if not md_path.exists():
        print(f"Error: Presentation file '{parsed.file}' not found.")
        return 1

    md_content = md_path.read_text(encoding="utf-8")
    deck = SlideDeck.from_markdown(md_content)

    if parsed.export_text:
        rendered_deck = []
        for idx, slide in enumerate(deck.slides):
            rendered_deck.append(
                render_slide(
                    slide,
                    current_index=idx,
                    total_slides=len(deck.slides),
                    run_code=parsed.run_code,
                )
            )
        out_path = Path(parsed.export_text)
        out_path.write_text("\n\n".join(rendered_deck), encoding="utf-8")
        print(f"Exported {len(deck.slides)} slides to '{parsed.export_text}'.")
        return 0

    if parsed.non_interactive:
        slide_idx = max(0, min(parsed.slide - 1, len(deck.slides) - 1))
        rendered = render_slide(
            deck.slides[slide_idx],
            current_index=slide_idx,
            total_slides=len(deck.slides),
            run_code=parsed.run_code,
        )
        print(rendered)
        return 0

    run_interactive_presentation(deck, auto_run_code=parsed.run_code)
    return 0


if __name__ == "__main__":
    sys.exit(main())
