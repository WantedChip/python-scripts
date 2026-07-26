import shutil
import tempfile
import unittest
from pathlib import Path

from main import (
    build_fs_tree,
    draw_ascii_bar,
    format_bytes,
    render_ascii_tree,
    render_top_heavy_items,
)


class TestFileSizeVisualizer(unittest.TestCase):
    def setUp(self):
        self.test_dir = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.test_dir)

    def test_format_bytes(self):
        self.assertEqual(format_bytes(500), "500 B")
        self.assertEqual(format_bytes(1024), "1.00 KB")
        self.assertEqual(format_bytes(1048576), "1.00 MB")
        self.assertEqual(format_bytes(1073741824), "1.00 GB")

    def test_draw_ascii_bar(self):
        bar = draw_ascii_bar(50.0, width=10)
        self.assertIn("█████░░░░░", bar)
        self.assertIn("50.0%", bar)

    def test_build_fs_tree(self):
        sub_dir = self.test_dir / "sub"
        sub_dir.mkdir()
        (sub_dir / "large.bin").write_bytes(b"x" * 2000)
        (self.test_dir / "small.txt").write_bytes(b"x" * 500)

        node = build_fs_tree(self.test_dir, max_depth=2)
        self.assertEqual(node.size, 2500)
        self.assertTrue(node.is_dir)
        self.assertEqual(len(node.children), 2)

    def test_render_ascii_tree(self):
        (self.test_dir / "test.txt").write_bytes(b"hello")
        node = build_fs_tree(self.test_dir, max_depth=2)
        tree_str = render_ascii_tree(node, max_depth=2)

        self.assertIn("test.txt", tree_str)
        self.assertIn("100.0%", tree_str)

    def test_render_top_heavy_items(self):
        (self.test_dir / "file1.bin").write_bytes(b"a" * 5000)
        (self.test_dir / "file2.bin").write_bytes(b"b" * 1000)

        node = build_fs_tree(self.test_dir, max_depth=2)
        report = render_top_heavy_items(node, top_n=5)

        self.assertIn("file1.bin", report)
        self.assertIn("file2.bin", report)


if __name__ == "__main__":
    unittest.main()
