import unittest

from main import calculate_column_widths, format_cell, parse_data, render_table


class TestAsciiTableGenerator(unittest.TestCase):
    """Unit tests for ASCII Table Generator functions."""

    def test_parse_csv_data(self):
        csv_input = "Name,Age,Role\nAlice,30,Engineer\nBob,25,Designer"
        rows = parse_data(csv_input, delimiter=",")
        self.assertEqual(len(rows), 3)
        self.assertEqual(rows[0], ["Name", "Age", "Role"])
        self.assertEqual(rows[1], ["Alice", "30", "Engineer"])

    def test_parse_tsv_data(self):
        tsv_input = "Name\tAge\nAlice\t30\nBob\t25"
        rows = parse_data(tsv_input)
        self.assertEqual(len(rows), 3)
        self.assertEqual(rows[1], ["Alice", "30"])

    def test_calculate_column_widths(self):
        rows = [["ID", "Product Name"], ["1", "Laptop"], ["100", "Mouse"]]
        widths = calculate_column_widths(rows)
        self.assertEqual(widths, [3, 12])

    def test_format_cell_alignment(self):
        self.assertEqual(format_cell("Hi", 5, "left"), "Hi   ")
        self.assertEqual(format_cell("Hi", 5, "right"), "   Hi")
        self.assertEqual(format_cell("Hi", 5, "center"), " Hi  ")

    def test_render_table_grid(self):
        rows = [["A", "B"], ["1", "2"]]
        table = render_table(rows, style_name="grid", align="left")
        self.assertIn("+---+---+", table)
        self.assertIn("| A | B |", table)

    def test_render_table_markdown(self):
        rows = [["Header1", "Header2"], ["Val1", "Val2"]]
        table = render_table(rows, style_name="markdown", align="left")
        self.assertIn("| Header1 | Header2 |", table)
        self.assertIn("|---------|---------|", table)


if __name__ == "__main__":
    unittest.main()
