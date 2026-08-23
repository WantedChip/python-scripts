import io
import shutil
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from typing import Tuple
from unittest.mock import patch

import main as fsv
from main import (
    NodeInfo,
    build_fs_tree,
    build_parser,
    collect_all_nodes,
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


class TestFormattingHelpers(unittest.TestCase):
    """Unit-scale formatting of byte sizes and percentage bars."""

    def test_format_bytes_terabyte_and_petabyte_scales(self) -> None:
        """Sizes beyond gigabytes format as TB and PB units."""
        self.assertEqual(format_bytes(1024**4), "1.00 TB")
        self.assertEqual(format_bytes(1024**5), "1.00 PB")
        self.assertEqual(format_bytes(1536), "1.50 KB")

    def test_draw_ascii_bar_clamps_out_of_range_percentages(self) -> None:
        """Percentages below 0 and above 100 clamp to the bar bounds."""
        empty = draw_ascii_bar(-10.0, width=8)
        full = draw_ascii_bar(150.0, width=8)

        self.assertIn("[░░░░░░░░]", empty)
        self.assertIn("0.0%", empty)
        self.assertIn("[████████]", full)
        self.assertIn("100.0%", full)


class TestTreeBuilding(unittest.TestCase):
    """Filesystem scanning: files as roots, guards, and depth limits."""

    def setUp(self) -> None:
        self.temp_dir = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.temp_dir, True)

    def test_single_file_root_returns_file_node(self) -> None:
        """Scanning a plain file path yields a file node with its size."""
        target = self.temp_dir / "solo.txt"
        target.write_bytes(b"12345")

        node = build_fs_tree(target)
        self.assertFalse(node.is_dir)
        self.assertEqual(node.size, 5)
        self.assertEqual(node.name, "solo.txt")
        self.assertEqual(node.children, [])

    def test_missing_root_raises_value_error(self) -> None:
        """A nonexistent root path raises ValueError."""
        with self.assertRaises(ValueError):
            build_fs_tree(self.temp_dir / "ghost")

    def test_unreadable_directory_yields_empty_children(self) -> None:
        """A PermissionError while listing leaves the node childless."""
        with patch.object(Path, "iterdir", side_effect=PermissionError("no access")):
            node = build_fs_tree(self.temp_dir, max_depth=1)

        self.assertTrue(node.is_dir)
        self.assertEqual(node.size, 0)
        self.assertEqual(node.children, [])

    def test_depth_limit_prunes_children_but_keeps_sizes(self) -> None:
        """At max_depth the subtree sizes count but children are pruned."""
        sub = self.temp_dir / "deep"
        sub.mkdir()
        (sub / "payload.bin").write_bytes(b"x" * 300)

        root = build_fs_tree(self.temp_dir, max_depth=0)
        self.assertEqual(root.size, 300)
        self.assertEqual(root.children, [])


class TestRenderingDetails(unittest.TestCase):
    """Tree and treemap rendering branches for connectors and paths."""

    def setUp(self) -> None:
        self.temp_dir = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.temp_dir, True)

    def test_collect_all_nodes_flattens_hierarchy(self) -> None:
        """collect_all_nodes returns the root plus every descendant."""
        child = NodeInfo(
            name="c.txt", path=self.temp_dir / "c.txt", is_dir=False, size=10
        )
        grandchild = NodeInfo(
            name="g.txt", path=self.temp_dir / "g.txt", is_dir=False, size=5
        )
        child.children.append(grandchild)
        root = NodeInfo(
            name="root", path=self.temp_dir, is_dir=True, size=15, children=[child]
        )

        names = [n.name for n in collect_all_nodes(root)]
        self.assertEqual(names, ["root", "c.txt", "g.txt"])

    def test_tree_uses_connectors_for_multiple_children(self) -> None:
        """Non-last children use ├── and the last uses └──."""
        (self.temp_dir / "a.txt").write_bytes(b"aaaa")
        (self.temp_dir / "b.txt").write_bytes(b"bb")

        node = build_fs_tree(self.temp_dir, max_depth=1)
        tree = render_ascii_tree(node, max_depth=1)

        self.assertIn("├──", tree)
        self.assertIn("└──", tree)

    def test_top_heavy_without_children_reports_placeholder(self) -> None:
        """An empty directory renders the 'no items' placeholder."""
        root = build_fs_tree(self.temp_dir, max_depth=1)
        self.assertEqual(render_top_heavy_items(root), "No child items found.")

    def test_top_heavy_falls_back_to_name_for_foreign_paths(self) -> None:
        """Children outside the root fall back to their bare name."""
        outside = self.temp_dir / "elsewhere"
        outside.mkdir()
        child = NodeInfo(
            name="far.txt", path=outside / "far.txt", is_dir=False, size=40
        )
        root = NodeInfo(
            name="root",
            path=self.temp_dir / "root",
            is_dir=True,
            size=100,
            children=[child],
        )

        report = render_top_heavy_items(root)
        self.assertIn("FILE", report)
        self.assertIn("| far.txt", report)


class TestCommandLine(unittest.TestCase):
    """CLI argument handling and end-to-end report generation."""

    def setUp(self) -> None:
        self.temp_dir = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.temp_dir, True)

    def _run_cli(self, *args: str) -> Tuple[int, str]:
        """Invoke main() capturing stdout; returns (code, output)."""
        buf = io.StringIO()
        with redirect_stdout(buf):
            code = fsv.main(list(args))
        return code, buf.getvalue()

    def test_build_parser_defaults_and_flags(self) -> None:
        """The parser exposes defaults for dir/depth/top/bar/style."""
        parsed = build_parser().parse_args([])
        self.assertEqual(parsed.dir, ".")
        self.assertEqual(parsed.depth, 2)
        self.assertEqual(parsed.top, 10)
        self.assertEqual(parsed.bar_width, 18)
        self.assertEqual(parsed.style, "all")

    def test_main_renders_both_styles_by_default(self) -> None:
        """Default style 'all' prints the tree plus top-heavy report."""
        (self.temp_dir / "data.bin").write_bytes(b"z" * 2048)

        code, out = self._run_cli("-d", str(self.temp_dir))

        self.assertEqual(code, 0)
        self.assertIn("Analyzing disk usage", out)
        self.assertIn("=== Disk Usage ASCII Tree ===", out)
        self.assertIn("Heaviest Files / Folders", out)
        self.assertIn("data.bin", out)

    def test_main_style_selection_limits_output(self) -> None:
        """--style tree or treemap prints only the matching section."""
        (self.temp_dir / "only.txt").write_bytes(b"q")

        code, out = self._run_cli("-d", str(self.temp_dir), "--style", "tree")
        self.assertEqual(code, 0)
        self.assertIn("ASCII Tree", out)
        self.assertNotIn("Heaviest Files", out)

        code, out = self._run_cli("-d", str(self.temp_dir), "--style", "treemap")
        self.assertEqual(code, 0)
        self.assertIn("Heaviest Files", out)
        self.assertNotIn("ASCII Tree ===", out)

    def test_main_missing_directory_exits_one_with_error(self) -> None:
        """A nonexistent --dir prints an error to stderr and exits 1."""
        missing = self.temp_dir / "vanished"
        err_buf = io.StringIO()

        with redirect_stderr(err_buf):
            code = fsv.main(["-d", str(missing)])

        self.assertEqual(code, 1)
        self.assertIn("does not exist", err_buf.getvalue())


if __name__ == "__main__":
    unittest.main()
