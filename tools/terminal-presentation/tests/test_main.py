"""Tests for the Terminal Presentation tool."""

import contextlib
import io
import runpy
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import main as main_module
from main import (
    CodeBlock,
    Slide,
    SlideDeck,
    build_parser,
    execute_snippet,
    get_key_press,
    highlight_code,
    main,
    render_slide,
    run_interactive_presentation,
)


class TestTerminalPresentation(unittest.TestCase):
    """Test cases for markdown parsing, ANSI highlighting, and rendering."""

    def test_slide_deck_from_markdown_divider(self):
        md = """# Slide 1
This is slide 1.

---

# Slide 2
- Bullet 1
- Bullet 2

```python
print("Hello World")
```
"""
        deck = SlideDeck.from_markdown(md)
        self.assertEqual(len(deck.slides), 2)
        self.assertEqual(deck.slides[0].title, "Slide 1")
        self.assertEqual(deck.slides[1].title, "Slide 2")
        self.assertEqual(len(deck.slides[1].code_blocks), 1)
        self.assertEqual(deck.slides[1].code_blocks[0].language, "python")

    def test_highlight_code(self):
        code = "def hello():\n    # A comment\n    return 'world'"
        highlighted = highlight_code(code, "python")
        self.assertIn("def", highlighted)
        self.assertIn("comment", highlighted)

    def test_execute_snippet_python(self):
        block = CodeBlock(language="python", code="print(2 + 3)", executable=True)
        output = execute_snippet(block)
        self.assertEqual(output, "5")

    def test_render_slide(self):
        slide = Slide(
            title="Test Title",
            raw_content="Intro text\n- Item 1\n- Item 2",
            code_blocks=[],
        )
        rendered = render_slide(slide, current_index=0, total_slides=1, width=80)
        self.assertIn("Test Title", rendered)
        self.assertIn("Item 1", rendered)
        self.assertIn("Slide 1/1", rendered)

    def test_render_slide_with_code_execution(self):
        slide = Slide(
            title="Code Demo",
            raw_content="```python\nprint('Exec Test')\n```",
            code_blocks=[
                CodeBlock(language="python", code="print('Exec Test')", executable=True)
            ],
        )
        rendered = render_slide(slide, current_index=0, total_slides=1, run_code=True)
        self.assertIn("Live Output:", rendered)
        self.assertIn("Exec Test", rendered)


class TestSlideParsing(unittest.TestCase):
    """Markdown parsing edge cases."""

    def test_empty_markdown_yields_placeholder_slide(self) -> None:
        """Blank input produces a single placeholder slide."""
        deck = SlideDeck.from_markdown("")
        self.assertEqual(len(deck.slides), 1)
        self.assertEqual(deck.slides[0].title, "Empty Deck")

    def test_h1_headers_split_slides_without_dividers(self) -> None:
        """'# ' headers create slide boundaries even without '---'."""
        md = "# Alpha\ncontent a\n# Beta\ncontent b"
        deck = SlideDeck.from_markdown(md)
        titles = [s.title for s in deck.slides]
        self.assertEqual(titles, ["Alpha", "Beta"])

    def test_non_executable_languages_are_flagged(self) -> None:
        """Only shell/python-ish languages are marked executable."""
        slide = SlideDeck._parse_single_slide("```js\nconsole.log(1)\n```")
        self.assertFalse(slide.code_blocks[0].executable)
        py_slide = SlideDeck._parse_single_slide("```PY\nprint(1)\n```")
        self.assertTrue(py_slide.code_blocks[0].executable)

    def test_unlabeled_fences_default_to_text_language(self) -> None:
        """Fences without a language tag fall back to 'text'."""
        slide = SlideDeck._parse_single_slide("```\nplain\n```")
        self.assertEqual(slide.code_blocks[0].language, "text")


class TestSnippetExecution(unittest.TestCase):
    """Subprocess execution paths with mocked process boundaries."""

    @staticmethod
    def make_result(
        stdout: str = "", stderr: str = "", returncode: int = 0
    ) -> subprocess.CompletedProcess:
        """Build a CompletedProcess stand-in for subprocess mocks."""
        return subprocess.CompletedProcess([], returncode, stdout, stderr)

    def test_bash_branch_invokes_shell_command(self) -> None:
        """Shell snippets spawn the platform shell with the code attached."""
        block = CodeBlock(language="bash", code="echo hi", executable=True)
        with mock.patch(
            "main.subprocess.run",
            return_value=self.make_result(stdout="hi"),
        ) as runner:
            out = execute_snippet(block)
        self.assertEqual(out, "hi")
        invoked_cmd = runner.call_args.args[0]
        self.assertIn(block.code, invoked_cmd)

    def test_unsupported_language_reports_message(self) -> None:
        """Unknown languages are reported instead of executed."""
        block = CodeBlock(language="ruby", code="puts 1", executable=False)
        self.assertIn("unsupported", execute_snippet(block))

    def test_stderr_and_exit_status_are_appended(self) -> None:
        """Non-empty stderr and nonzero exit codes appear in the output."""
        result = self.make_result(stdout="partial", stderr="boom", returncode=3)
        block = CodeBlock(language="python", code="x", executable=True)
        with mock.patch("main.subprocess.run", return_value=result):
            out = execute_snippet(block)
        self.assertIn("partial", out)
        self.assertIn("[stderr]: boom", out)
        self.assertIn("[exit status: 3]", out)

    def test_timeout_returns_notice(self) -> None:
        """Timeouts produce a friendly timeout message."""
        block = CodeBlock(language="py", code="while True: pass")
        with mock.patch(
            "main.subprocess.run",
            side_effect=subprocess.TimeoutExpired(cmd=[], timeout=7),
        ):
            out = execute_snippet(block, timeout=7)
        self.assertIn("[Execution Timed Out (7s)]", out)

    def test_generic_failure_returns_error_message(self) -> None:
        """Unexpected execution failures are captured as messages."""
        block = CodeBlock(language="sh", code="exit 1")
        with mock.patch("main.subprocess.run", side_effect=OSError("spawn failed")):
            out = execute_snippet(block)
        self.assertIn("[Execution Error: spawn failed]", out)

    def test_empty_output_uses_placeholder(self) -> None:
        """Silent successful runs report '[No Output]'."""
        block = CodeBlock(language="python", code="pass")
        with mock.patch("main.subprocess.run", return_value=self.make_result()):
            self.assertEqual(execute_snippet(block), "[No Output]")


class TestRenderSlideDetails(unittest.TestCase):
    """Rendering branches beyond the basic cases."""

    def test_secondary_headers_render_as_subheaders(self) -> None:
        """In-body '# Other' lines render as highlighted subheaders."""
        slide = Slide(
            title="Main",
            raw_content="# Main\nbody\n## Section A",
            code_blocks=[],
        )
        rendered = render_slide(slide, current_index=0, total_slides=1)
        self.assertIn("# Section A", rendered)

    def test_title_header_line_is_not_duplicated(self) -> None:
        """The slide's own title header line is skipped in the body."""
        slide = Slide(title="Solo", raw_content="# Solo\nplain line")
        rendered = render_slide(slide, current_index=0, total_slides=1)
        body_lines = [
            ln for ln in rendered.splitlines() if "plain line" in ln or "# Solo" in ln
        ]
        self.assertEqual(len(body_lines), 1)
        self.assertIn("plain line", body_lines[0])

    def test_star_bullets_render_like_dashes(self) -> None:
        """'* item' bullets also render with bullet glyphs."""
        slide = Slide(title="Bullets", raw_content="- dash\n* star")
        rendered = render_slide(slide, current_index=0, total_slides=1)
        star_rows = [ln for ln in rendered.splitlines() if "star" in ln]
        self.assertEqual(len(star_rows), 1)
        self.assertIn("\u2022", star_rows[0])


class TestKeyPress(unittest.TestCase):
    """Single keypress reader on the native Windows path."""

    def test_regular_key_is_decoded_and_lowercased(self) -> None:
        """A plain keystroke decodes to its lowercase character."""
        fake_msvcrt = mock.Mock()
        fake_msvcrt.getch.return_value = b"Q"
        with mock.patch.object(main_module.sys, "platform", "win32"):
            with mock.patch.dict(sys.modules, {"msvcrt": fake_msvcrt}):
                self.assertEqual(get_key_press(), "q")

    def test_extended_key_prefix_reads_second_byte(self) -> None:
        """Arrow/special keys send a two-byte sequence; second byte wins."""
        fake_msvcrt = mock.Mock()
        fake_msvcrt.getch.side_effect = [b"\xe0", b"M"]
        with mock.patch.object(main_module.sys, "platform", "win32"):
            with mock.patch.dict(sys.modules, {"msvcrt": fake_msvcrt}):
                self.assertEqual(get_key_press(), "m")

    def test_posix_tty_read_returns_lowercased_char(self) -> None:
        """The termios/tty branch reads one raw char from stdin."""
        fake_termios = mock.Mock()
        fake_tty = mock.Mock()
        fake_stdin = mock.Mock()
        fake_stdin.fileno.return_value = 0
        fake_stdin.read.return_value = "H"
        with mock.patch.dict(sys.modules, {"termios": fake_termios, "tty": fake_tty}):
            with mock.patch.object(main_module.sys, "platform", "posix"):
                with mock.patch.object(sys, "stdin", fake_stdin):
                    self.assertEqual(get_key_press(), "h")
                    fake_termios.tcsetattr.assert_called_once()


class TestInteractiveLoop(unittest.TestCase):
    """The keyboard-driven slideshow loop with scripted input."""

    DECK = SlideDeck(
        slides=[
            Slide(title="First", raw_content="one"),
            Slide(title="Second", raw_content="two"),
        ]
    )

    def test_navigation_keys_drive_slideshow(self) -> None:
        """next/prev/exec/quit keys navigate and toggle live execution."""
        buffer = io.StringIO()
        keys = iter(["e", "n", "p", " ", "b", "\r", "unknown", "q"])
        with mock.patch.object(main_module.os, "system"):
            with mock.patch.object(
                main_module, "get_key_press", side_effect=lambda: next(keys)
            ):
                with contextlib.redirect_stdout(buffer):
                    run_interactive_presentation(self.DECK)
        output = buffer.getvalue()
        self.assertIn("First", output)
        self.assertIn("Second", output)
        # Index 0 is rendered at start, after 'p', and after 'b'.
        self.assertGreaterEqual(output.count("First"), 3)


class TestCommandLine(unittest.TestCase):
    """CLI entry point behaviors."""

    MD_CONTENT = "# Intro\nhello world\n---\n# Setup\n- step one"

    @staticmethod
    def write_md(directory: Path, name: str = "deck.md") -> Path:
        """Write the sample deck into ``directory``."""
        path = directory / name
        path.write_text(TestCommandLine.MD_CONTENT, encoding="utf-8")
        return path

    def test_parser_defaults(self) -> None:
        """Positional file plus documented default values."""
        parsed = build_parser().parse_args(["deck.md"])
        self.assertEqual(parsed.file, "deck.md")
        self.assertEqual(parsed.slide, 1)
        self.assertFalse(parsed.run_code)
        self.assertFalse(parsed.non_interactive)
        self.assertIsNone(parsed.export_text)

    def test_missing_file_returns_one(self) -> None:
        """Unknown presentation files yield exit code 1."""
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            code = main(["ghost-deck.md"])
        self.assertEqual(code, 1)
        self.assertIn("Error: Presentation file", buffer.getvalue())

    def test_export_text_writes_all_slides(self) -> None:
        """--export-text renders every slide into one output file."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            directory = Path(tmp_dir)
            deck_path = self.write_md(directory)
            export_path = directory / "out.txt"
            buffer = io.StringIO()
            with contextlib.redirect_stdout(buffer):
                code = main([str(deck_path), "--export-text", str(export_path)])
            self.assertEqual(code, 0)
            exported = export_path.read_text(encoding="utf-8")
        self.assertIn("Exported 2 slides", buffer.getvalue())
        self.assertIn("Intro", exported)
        self.assertIn("Setup", exported)

    def test_non_interactive_renders_requested_slide(self) -> None:
        """--slide picks a specific slide; out-of-range values clamp."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            directory = Path(tmp_dir)
            deck_path = self.write_md(directory)
            buffer = io.StringIO()
            with contextlib.redirect_stdout(buffer):
                code = main([str(deck_path), "--non-interactive"])
            self.assertEqual(code, 0)
            self.assertIn("Intro", buffer.getvalue())

            buffer2 = io.StringIO()
            with contextlib.redirect_stdout(buffer2):
                code2 = main([str(deck_path), "--non-interactive", "--slide", "99"])
            self.assertEqual(code2, 0)
            self.assertIn("Setup", buffer2.getvalue())

    def test_interactive_default_delegates_to_loop(self) -> None:
        """Without flags the interactive loop receives the parsed deck."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            deck_path = self.write_md(Path(tmp_dir))
            with mock.patch.object(main_module, "run_interactive_presentation") as loop:
                code = main([str(deck_path), "--run-code"])
        self.assertEqual(code, 0)
        loop.assert_called_once()
        (deck_arg,) = loop.call_args.args
        self.assertEqual(len(deck_arg.slides), 2)
        self.assertTrue(loop.call_args.kwargs["auto_run_code"])

    def test_dunder_main_exits_zero(self) -> None:
        """Executing main.py as a program renders non-interactively."""
        entry = str(Path(__file__).resolve().parents[1] / "main.py")
        with tempfile.TemporaryDirectory() as tmp_dir:
            deck_path = self.write_md(Path(tmp_dir))
            argv = [entry, str(deck_path), "--non-interactive"]
            buffer = io.StringIO()
            with mock.patch.object(sys, "argv", argv):
                with contextlib.redirect_stdout(buffer):
                    with self.assertRaises(SystemExit) as ctx:
                        runpy.run_path(entry, run_name="__main__")
            self.assertEqual(ctx.exception.code, 0)
        self.assertIn("Intro", buffer.getvalue())


if __name__ == "__main__":
    unittest.main()
