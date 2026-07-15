"""Compare two git revisions and generate a factual changelog from

actual code changes and AST analysis of Python structures.
"""

# pylint: disable=duplicate-code

import argparse
import ast
import hashlib
import logging
import os
import subprocess  # nosec
import sys
from typing import Dict, List, Optional, Tuple


class GitCommandError(Exception):
    """Exception raised when a Git command fails."""


def run_git(args: List[str], cwd: Optional[str] = None) -> str:
    """Run a Git command and return stdout.

    Args:
        args: List of Git arguments.
        cwd: Working directory.

    Returns:
        Decoded stdout.

    Raises:
        GitCommandError: If command fails.
    """
    cmd = ["git"] + args
    logging.debug("Running: %s", " ".join(cmd))
    try:
        result = subprocess.run(  # nosec
            cmd,
            cwd=cwd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=True,
        )
        return result.stdout.strip()
    except subprocess.CalledProcessError as err:
        raise GitCommandError(
            f"Git command failed: {' '.join(cmd)}. Error: {err.stderr.strip()}"
        ) from err


def get_changed_files(
    repo_path: str, from_ref: str, to_ref: str
) -> Tuple[List[str], List[str], List[str]]:
    """Get lists of added, deleted, and modified files between two refs.

    Args:
        repo_path: Path to git repository.
        from_ref: Start revision.
        to_ref: End revision.

    Returns:
        A tuple of (added_files, deleted_files, modified_files).
    """
    try:
        output = run_git(["diff", "--name-status", from_ref, to_ref], cwd=repo_path)
    except GitCommandError as err:
        print(f"Error diffing refs: {err}")
        sys.exit(1)

    added, deleted, modified = [], [], []
    for line in output.splitlines():
        if not line.strip():
            continue
        parts = line.split(maxsplit=1)
        if len(parts) < 2:
            continue
        status, path = parts[0], parts[1]
        if status.startswith("A"):
            added.append(path)
        elif status.startswith("D"):
            deleted.append(path)
        elif status.startswith("M"):
            modified.append(path)

    return added, deleted, modified


def get_file_content(repo_path: str, ref: str, path: str) -> Optional[str]:
    """Retrieve file content at a specific git ref.

    Args:
        repo_path: Path to git repository.
        ref: Git reference.
        path: File path.

    Returns:
        File contents as string, or None if failed.
    """
    try:
        return run_git(["show", f"{ref}:{path}"], cwd=repo_path)
    except GitCommandError:
        return None


class FunctionInfo:  # pylint: disable=too-few-public-methods
    """Stores structural signature info for a function or method."""

    def __init__(
        self,
        name: str,
        args_str: str,
        returns_str: str,
        docstring: Optional[str],
        body_hash: str,
    ) -> None:
        self.name = name
        self.args_str = args_str
        self.returns_str = returns_str
        self.docstring = docstring
        self.body_hash = body_hash

    def signature_equals(self, other: "FunctionInfo") -> bool:
        """Check if parameter and return type signatures match."""
        return self.args_str == other.args_str and self.returns_str == other.returns_str


class ClassInfo:  # pylint: disable=too-few-public-methods
    """Stores structural info for a class definition."""

    def __init__(self, name: str, bases: List[str]) -> None:
        self.name = name
        self.bases = bases
        self.methods: Dict[str, FunctionInfo] = {}


def parse_structure(
    source_code: str,
) -> Tuple[Dict[str, FunctionInfo], Dict[str, ClassInfo]]:
    """Parse Python source code and extract functions and classes metadata.

    Args:
        source_code: Python source code.

    Returns:
        A tuple of (functions_dict, classes_dict).
    """
    functions: Dict[str, FunctionInfo] = {}
    classes: Dict[str, ClassInfo] = {}

    try:
        tree = ast.parse(source_code)
    except SyntaxError:
        return functions, classes

    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            func_name = node.name
            args_str = ast.unparse(node.args)
            returns_str = ast.unparse(node.returns) if node.returns else "None"
            doc = ast.get_docstring(node)
            body_hash = hashlib.sha256(ast.unparse(node).encode("utf-8")).hexdigest()
            functions[func_name] = FunctionInfo(
                func_name, args_str, returns_str, doc, body_hash
            )

        elif isinstance(node, ast.ClassDef):
            class_name = node.name
            bases = [ast.unparse(base) for base in node.bases]
            class_info = ClassInfo(class_name, bases)

            # Extract class methods
            for subnode in node.body:
                if isinstance(subnode, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    method_name = subnode.name
                    args_str = ast.unparse(subnode.args)
                    returns_str = (
                        ast.unparse(subnode.returns) if subnode.returns else "None"
                    )
                    doc = ast.get_docstring(subnode)
                    body_hash = hashlib.sha256(
                        ast.unparse(subnode).encode("utf-8")
                    ).hexdigest()
                    class_info.methods[method_name] = FunctionInfo(
                        method_name, args_str, returns_str, doc, body_hash
                    )

            classes[class_name] = class_info

    return functions, classes


def diff_python_structure(  # pylint: disable=too-many-branches,too-many-locals
    from_source: str, to_source: str
) -> Dict[str, List[str]]:
    """Diff Python module structures.

    Args:
        from_source: Python source code in base ref.
        to_source: Python source code in target ref.

    Returns:
        Dictionary detailing changes in categories (added, removed, modified).
    """
    changes: Dict[str, List[str]] = {
        "added_funcs": [],
        "removed_funcs": [],
        "modified_funcs": [],
        "added_classes": [],
        "removed_classes": [],
        "modified_classes": [],
    }

    from_funcs, from_classes = parse_structure(from_source)
    to_funcs, to_classes = parse_structure(to_source)

    # 1. Diff top-level functions
    for name, info in to_funcs.items():
        if name not in from_funcs:
            changes["added_funcs"].append(
                f"`def {name}({info.args_str}) -> {info.returns_str}`"
            )
        else:
            prev_info = from_funcs[name]
            if not info.signature_equals(prev_info):
                desc = (
                    f"`def {name}` signature changed:\n"
                    f"      - Before: `({prev_info.args_str}) -> "
                    f"{prev_info.returns_str}`\n"
                    f"      - After: `({info.args_str}) -> {info.returns_str}`"
                )
                changes["modified_funcs"].append(desc)
            elif info.body_hash != prev_info.body_hash:
                changes["modified_funcs"].append(f"`def {name}` logic updated")

    for name in from_funcs:
        if name not in to_funcs:
            changes["removed_funcs"].append(f"`def {name}`")

    # 2. Diff classes
    for name, cinfo in to_classes.items():
        if name not in from_classes:
            bases_str = f"({', '.join(cinfo.bases)})" if cinfo.bases else ""
            changes["added_classes"].append(f"`class {name}{bases_str}`")
        else:
            prev_cinfo = from_classes[name]
            # Check class bases modification
            if cinfo.bases != prev_cinfo.bases:
                changes["modified_classes"].append(
                    f"`class {name}` base classes modified: "
                    f"{prev_cinfo.bases} -> {cinfo.bases}"
                )

            # Diff methods within class
            for mname, minfo in cinfo.methods.items():
                if mname not in prev_cinfo.methods:
                    changes["modified_classes"].append(
                        f"`class {name}` added method "
                        f"`def {mname}({minfo.args_str}) -> {minfo.returns_str}`"
                    )
                else:
                    prev_minfo = prev_cinfo.methods[mname]
                    if not minfo.signature_equals(prev_minfo):
                        desc = (
                            f"`class {name}` method `def {mname}` signature changed:\n"
                            f"      - Before: `({prev_minfo.args_str}) -> "
                            f"{prev_minfo.returns_str}`\n"
                            f"      - After: `({minfo.args_str}) -> "
                            f"{minfo.returns_str}`"
                        )
                        changes["modified_classes"].append(desc)
                    elif minfo.body_hash != prev_minfo.body_hash:
                        changes["modified_classes"].append(
                            f"`class {name}` method `def {mname}` updated"
                        )

            for mname in prev_cinfo.methods:
                if mname not in cinfo.methods:
                    changes["modified_classes"].append(
                        f"`class {name}` removed method `def {mname}`"
                    )

    for name in from_classes:
        if name not in to_classes:
            changes["removed_classes"].append(f"`class {name}`")

    return changes


# pylint: disable=too-many-arguments,too-many-positional-arguments
# pylint: disable=too-many-nested-blocks,too-many-branches
def generate_markdown_changelog(
    from_ref: str,
    to_ref: str,
    added: List[str],
    deleted: List[str],
    modified: List[str],
    repo_path: str,
) -> str:
    """Compile facts into a Markdown document.

    Args:
        from_ref: Start ref.
        to_ref: End ref.
        added: Added files.
        deleted: Deleted files.
        modified: Modified files.
        repo_path: Repository path.

    Returns:
        Changelog content as markdown string.
    """
    lines = [
        f"# Changelog (from reality): {from_ref} to {to_ref}",
        "",
        "## Summary",
        f"- **Added files**: {len(added)}",
        f"- **Deleted files**: {len(deleted)}",
        f"- **Modified files**: {len(modified)}",
        "",
    ]

    if added:
        lines.append("## Added Files")
        for f in added:
            lines.append(f"- `{f}`")
        lines.append("")

    if deleted:
        lines.append("## Deleted Files")
        for f in deleted:
            lines.append(f"- `{f}`")
        lines.append("")

    if modified:
        lines.append("## Code Modifications")
        for f in modified:
            lines.append(f"### `{f}`")

            if f.endswith(".py"):
                from_source = get_file_content(repo_path, from_ref, f)
                to_source = get_file_content(repo_path, to_ref, f)

                if from_source is not None and to_source is not None:
                    diffs = diff_python_structure(from_source, to_source)
                    has_changes = False

                    for key in [
                        "added_funcs",
                        "removed_funcs",
                        "modified_funcs",
                        "added_classes",
                        "removed_classes",
                        "modified_classes",
                    ]:
                        if diffs[key]:
                            has_changes = True
                            # Format title
                            title = key.replace("_", " ").title()
                            lines.append(f"  * **{title}**:")
                            for item in diffs[key]:
                                lines.append(f"    - {item}")

                    if not has_changes:
                        lines.append(
                            "  * Non-structural changes (docstrings/whitespace/etc.)"
                        )
                else:
                    lines.append("  * File modified (could not parse source/AST).")
            else:
                lines.append("  * File modified.")
            lines.append("")

    return "\n".join(lines)


def main() -> None:
    """Main CLI execution."""
    parser = argparse.ArgumentParser(
        description=(
            "Generate a factual changelog comparing two "
            "revisions by performing AST diff analysis."
        )
    )
    parser.add_argument("from_ref", help="Start revision (tag/commit/branch).")
    parser.add_argument("to_ref", help="End revision (tag/commit/branch).")
    parser.add_argument(
        "-r",
        "--repo",
        default=".",
        help="Path to git repository (default: current directory).",
    )
    parser.add_argument(
        "-o",
        "--output",
        help="Path to write the markdown changelog output.",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Enable verbose logging output.",
    )

    args = parser.parse_args()

    log_level = logging.DEBUG if args.verbose else logging.WARNING
    logging.basicConfig(level=log_level, format="%(levelname)s: %(message)s")

    repo_path = args.repo
    if not os.path.exists(os.path.join(repo_path, ".git")):
        print(f"Error: '{repo_path}' is not a valid Git repository.")
        sys.exit(1)

    added, deleted, modified = get_changed_files(repo_path, args.from_ref, args.to_ref)
    changelog = generate_markdown_changelog(
        args.from_ref,
        args.to_ref,
        added,
        deleted,
        modified,
        repo_path,
    )

    if args.output:
        try:
            with open(args.output, "w", encoding="utf-8") as f:
                f.write(changelog)
            print(f"Changelog successfully written to: {args.output}")
        except OSError as err:
            print(f"Error writing changelog to file: {err}")
            sys.exit(1)
    else:
        print(changelog)


if __name__ == "__main__":
    main()
