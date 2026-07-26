#!/usr/bin/env python3
"""File Size Visualizer CLI.

Features:
- Recursive directory disk usage calculation
- Customizable maximum traversal depth
- Human-readable byte formatting (B, KB, MB, GB, TB)
- ASCII tree hierarchy visual rendering with relative bar charts
- Top N heaviest files/folders treemap breakdown
"""

# pylint: disable=too-many-branches,too-many-statements
# pylint: disable=too-many-locals,too-many-arguments,too-many-positional-arguments
# pylint: disable=too-many-instance-attributes,too-few-public-methods

import argparse
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional


@dataclass
class NodeInfo:
    """Represents file system node with disk usage metrics."""

    name: str
    path: Path
    is_dir: bool
    size: int
    children: List["NodeInfo"] = field(default_factory=list)


def format_bytes(size: int) -> str:
    """Formats byte integer into human-readable string (e.g. 1.45 MB)."""
    float_size = float(size)
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if float_size < 1024:
            return f"{float_size:.2f} {unit}" if unit != "B" else f"{size} B"
        float_size /= 1024.0
    return f"{float_size:.2f} PB"


def draw_ascii_bar(percentage: float, width: int = 20) -> str:
    """Generates ASCII progress bar string representing percentage usage."""
    percentage = max(0.0, min(100.0, percentage))
    filled_len = int(round(width * percentage / 100.0))
    bar_str = "█" * filled_len + "░" * (width - filled_len)
    return f"[{bar_str}] {percentage:5.1f}%"


def build_fs_tree(
    directory: Path, max_depth: int = 2, current_depth: int = 0
) -> NodeInfo:
    """Scans filesystem up to max_depth and calculates sizes."""
    if not directory.exists():
        raise ValueError(f"Path '{directory}' does not exist.")

    if directory.is_file():
        try:
            size = directory.stat().st_size
        except (PermissionError, FileNotFoundError):
            size = 0
        return NodeInfo(name=directory.name, path=directory, is_dir=False, size=size)

    total_size = 0
    children: List[NodeInfo] = []

    try:
        entries = list(directory.iterdir())
    except (PermissionError, FileNotFoundError):
        entries = []

    for entry in entries:
        try:
            if entry.is_file():
                file_size = entry.stat().st_size
                total_size += file_size
                if current_depth < max_depth:
                    node = NodeInfo(
                        name=entry.name, path=entry, is_dir=False, size=file_size
                    )
                    children.append(node)
            elif entry.is_dir():
                # Traverse sub-directory
                child_node = build_fs_tree(
                    directory=entry,
                    max_depth=max_depth,
                    current_depth=current_depth + 1,
                )
                total_size += child_node.size
                if current_depth < max_depth:
                    children.append(child_node)
        except (PermissionError, FileNotFoundError):
            continue

    # Sort children by size descending
    children.sort(key=lambda c: c.size, reverse=True)

    return NodeInfo(
        name=directory.name or str(directory),
        path=directory,
        is_dir=True,
        size=total_size,
        children=children,
    )


def render_ascii_tree(
    node: NodeInfo,
    max_depth: int = 2,
    bar_width: int = 20,
    prefix: str = "",
    is_last: bool = True,
    current_depth: int = 0,
    parent_size: Optional[int] = None,
) -> str:
    """Renders hierarchical ASCII tree with disk size percentage bar charts."""
    lines: List[str] = []
    if parent_size is not None:
        root_total = parent_size
    else:
        root_total = node.size if node.size > 0 else 1

    pct = (node.size / root_total) * 100.0 if root_total > 0 else 0.0

    bar_str = draw_ascii_bar(pct, width=bar_width)
    size_str = format_bytes(node.size).rjust(10)

    if current_depth == 0:
        lines.append(f"{node.name}/ {bar_str} ({size_str})")
    else:
        connector = "└── " if is_last else "├── "
        icon = "/" if node.is_dir else ""
        lines.append(f"{prefix}{connector}{node.name}{icon} {bar_str} ({size_str})")

    if current_depth < max_depth and node.children:
        child_prefix = prefix + ("    " if is_last else "│   ")
        count = len(node.children)
        for idx, child in enumerate(node.children):
            last_child = idx == count - 1
            lines.append(
                render_ascii_tree(
                    node=child,
                    max_depth=max_depth,
                    bar_width=bar_width,
                    prefix=child_prefix,
                    is_last=last_child,
                    current_depth=current_depth + 1,
                    parent_size=node.size,
                )
            )

    return "\n".join(lines)


def collect_all_nodes(node: NodeInfo) -> List[NodeInfo]:
    """Flattens NodeInfo tree into a list of all nodes."""
    nodes = [node]
    for child in node.children:
        nodes.extend(collect_all_nodes(child))
    return nodes


def render_top_heavy_items(
    root_node: NodeInfo, top_n: int = 10, bar_width: int = 25
) -> str:
    """Renders a report listing top N largest items."""
    all_nodes = collect_all_nodes(root_node)
    # Exclude root node itself
    filtered_nodes = [n for n in all_nodes if n.path != root_node.path]
    filtered_nodes.sort(key=lambda n: n.size, reverse=True)

    top_items = filtered_nodes[:top_n]
    if not top_items:
        return "No child items found."

    lines = [
        f"=== Top {len(top_items)} Heaviest Files / Folders ===",
        f"{'Type':<6} | {'Disk Size':<10} | {'Usage %':<30} | Path",
        "-" * 80,
    ]

    total_size = root_node.size if root_node.size > 0 else 1

    for item in top_items:
        node_type = "DIR" if item.is_dir else "FILE"
        size_str = format_bytes(item.size)
        pct = (item.size / total_size) * 100.0
        bar_str = draw_ascii_bar(pct, width=bar_width)

        rel_path_str: str
        try:
            rel_path_str = str(item.path.relative_to(root_node.path))
        except ValueError:
            rel_path_str = item.path.name

        lines.append(
            f"{node_type:<6} | {size_str:>10} | {bar_str:<30} | {rel_path_str}"
        )

    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    """Build CLI parser."""
    desc = "Generate ASCII tree and treemap-style reports of disk " + "usage."
    parser = argparse.ArgumentParser(description=desc)
    parser.add_argument(
        "--dir",
        "-d",
        default=".",
        help="Root directory to analyze (default: current directory)",
    )
    parser.add_argument(
        "--depth",
        type=int,
        default=2,
        help="Maximum tree traversal depth (default: 2)",
    )
    parser.add_argument(
        "--top",
        type=int,
        default=10,
        help="Number of top heavy items to report (default: 10)",
    )
    parser.add_argument(
        "--bar-width",
        type=int,
        default=18,
        help="Width of ASCII visual progress bar (default: 18)",
    )
    parser.add_argument(
        "--style",
        choices=["tree", "treemap", "all"],
        default="all",
        help="Visualization mode output style (default: all)",
    )
    return parser


def main(args: Optional[List[str]] = None) -> int:
    """CLI entrypoint for file size visualizer."""
    parser = build_parser()
    parsed = parser.parse_args(args)
    root_path = Path(parsed.dir).resolve()

    if not root_path.exists():
        msg = f"Error: Directory '{root_path}' does not exist."
        print(msg, file=sys.stderr)
        return 1

    print(f"Analyzing disk usage for '{root_path}'...\n")
    fs_tree = build_fs_tree(directory=root_path, max_depth=parsed.depth)

    if parsed.style in ("tree", "all"):
        print("=== Disk Usage ASCII Tree ===")
        tree_output = render_ascii_tree(
            node=fs_tree, max_depth=parsed.depth, bar_width=parsed.bar_width
        )
        print(tree_output)
        print()

    if parsed.style in ("treemap", "all"):
        top_output = render_top_heavy_items(
            root_node=fs_tree, top_n=parsed.top, bar_width=parsed.bar_width
        )
        print(top_output)

    return 0


if __name__ == "__main__":
    sys.exit(main())
