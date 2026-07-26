import unittest

from main import (
    CodeBlock,
    Slide,
    SlideDeck,
    execute_snippet,
    highlight_code,
    render_slide,
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


if __name__ == "__main__":
    unittest.main()
