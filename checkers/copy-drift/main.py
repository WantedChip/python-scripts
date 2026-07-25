"""Copy Drift Checker: Discover structurally similar code blocks.

Analyzes source code blocks for structural similarity (n-gram / token Jaccard)
and queries Git history to identify maintenance-coupled blocks where one block
was updated but sibling blocks were left out of sync.
"""

# pylint: disable=too-many-arguments,too-many-positional-arguments
# pylint: disable=too-many-locals,too-many-branches

import argparse
import ast
import difflib
import json
import keyword
import os
import re
import subprocess  # nosec B404
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple


@dataclass
class CodeBlock:
    """Represents a code or configuration block within a file."""

    file_path: str
    start_line: int
    end_line: int
    name: str
    content: str
    normalized_tokens: List[str]


@dataclass
class DriftReport:
    """Represents detected copy drift between two structurally similar blocks."""

    updated_file: str
    updated_range: str
    outdated_file: str
    outdated_range: str
    similarity: float
    historical_coupling_commits: int
    patch_suggestion: str


def tokenize_code(code: str) -> List[str]:
    """Tokenize code content into normalized structural tokens."""
    # Strip comments and literal values to compare AST structural shape
    code_clean = re.sub(r"#.*", "", code)
    code_clean = re.sub(r"(['\"]).*?\1", "STR", code_clean)
    code_clean = re.sub(r"\b\d+(?:\.\d+)?\b", "NUM", code_clean)
    tokens = re.findall(r"\w+", code_clean)
    normalized = []
    for t in tokens:
        t_lower = t.lower()
        if keyword.iskeyword(t_lower) or t in ("STR", "NUM"):
            normalized.append(t_lower)
        else:
            normalized.append("var")
    return [t for t in normalized if len(t) >= 1]


def compute_ngrams(tokens: List[str], n: int = 3) -> Set[Tuple[str, ...]]:
    """Generate n-grams from a list of tokens."""
    if len(tokens) < n:
        return {tuple(tokens)}
    return {tuple(tokens[i : i + n]) for i in range(len(tokens) - n + 1)}  # noqa: E203


def jaccard_similarity(set1: Set[Tuple[str, ...]], set2: Set[Tuple[str, ...]]) -> float:
    """Compute Jaccard similarity coefficient between two sets."""
    if not set1 or not set2:
        return 0.0
    intersection = len(set1.intersection(set2))
    union = len(set1.union(set2))
    return intersection / union if union > 0 else 0.0


def extract_blocks_from_file(file_path: Path, min_lines: int = 4) -> List[CodeBlock]:
    """Extract code/config blocks from a file using AST or line-chunking."""
    blocks: List[CodeBlock] = []
    try:
        content = file_path.read_text(encoding="utf-8")
    except Exception:  # nosec B110 # pylint: disable=broad-exception-caught
        return blocks

    lines = content.splitlines()

    # Try Python AST block extraction for Python files
    if file_path.suffix == ".py":
        try:
            tree = ast.parse(content, filename=str(file_path))
            for node in ast.walk(tree):
                is_fn = isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                is_cls = isinstance(node, ast.ClassDef)
                if is_fn or is_cls:
                    start = getattr(node, "lineno", 1)
                    end = getattr(node, "end_lineno", start)
                    if (end - start + 1) >= min_lines:
                        block_lines = lines[start - 1 : end]  # noqa: E203
                        block_content = "\n".join(block_lines)
                        tokens = tokenize_code(block_content)
                        blocks.append(
                            CodeBlock(
                                file_path=str(file_path),
                                start_line=start,
                                end_line=end,
                                name=getattr(node, "name", "block"),
                                content=block_content,
                                normalized_tokens=tokens,
                            )
                        )
            if blocks:
                return blocks
        except Exception:  # nosec B110 # pylint: disable=broad-exception-caught
            pass

    # Generic chunk extraction (chunking non-empty paragraph blocks)
    current_block: List[str] = []
    start_line = 1

    for idx, line in enumerate(lines, 1):
        if line.strip():
            if not current_block:
                start_line = idx
            current_block.append(line)
        else:
            if len(current_block) >= min_lines:
                block_content = "\n".join(current_block)
                tokens = tokenize_code(block_content)
                blocks.append(
                    CodeBlock(
                        file_path=str(file_path),
                        start_line=start_line,
                        end_line=idx - 1,
                        name=f"block_L{start_line}",
                        content=block_content,
                        normalized_tokens=tokens,
                    )
                )
            current_block = []

    if len(current_block) >= min_lines:
        block_content = "\n".join(current_block)
        tokens = tokenize_code(block_content)
        blocks.append(
            CodeBlock(
                file_path=str(file_path),
                start_line=start_line,
                end_line=len(lines),
                name=f"block_L{start_line}",
                content=block_content,
                normalized_tokens=tokens,
            )
        )

    return blocks


def get_git_commit_history(repo_dir: Path, depth: int = 100) -> Dict[str, Set[str]]:
    """Map file paths to commit hashes in recent git history."""
    file_commits: Dict[str, Set[str]] = {}
    try:
        cmd = [
            "git",
            "log",
            f"-n{depth}",
            "--name-only",
            "--pretty=format:COMMIT:%H",
        ]
        result = subprocess.run(  # nosec B603
            cmd,
            cwd=str(repo_dir),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=True,
        )
        current_commit = ""
        for line in result.stdout.splitlines():
            line = line.strip()
            if line.startswith("COMMIT:"):
                current_commit = line.split(":", 1)[1]
            elif line and current_commit:
                full_path = str((repo_dir / line).resolve())
                if full_path not in file_commits:
                    file_commits[full_path] = set()
                file_commits[full_path].add(current_commit)
    except Exception:  # nosec B110 # pylint: disable=broad-exception-caught
        pass
    return file_commits


def get_file_last_mtime(file_path: str) -> float:
    """Get file modification time."""
    try:
        return os.path.getmtime(file_path)
    except Exception:  # nosec B110 # pylint: disable=broad-exception-caught
        return 0.0


def generate_patch(src_block: CodeBlock, target_block: CodeBlock) -> str:
    """Generate unified diff patch to sync target_block with src_block."""
    diff = difflib.unified_diff(
        target_block.content.splitlines(),
        src_block.content.splitlines(),
        fromfile=f"{target_block.file_path}:{target_block.start_line}",
        tofile=f"{src_block.file_path}:{src_block.start_line}",
        lineterm="",
    )
    return "\n".join(diff)


def detect_copy_drift(
    blocks: List[CodeBlock],
    similarity_threshold: float = 0.75,
    file_commits: Optional[Dict[str, Set[str]]] = None,
) -> List[DriftReport]:
    """Detect copy drift among structural blocks."""
    reports: List[DriftReport] = []
    file_commits = file_commits or {}

    # Precompute n-grams for all blocks
    block_ngrams = [compute_ngrams(b.normalized_tokens) for b in blocks]

    num_blocks = len(blocks)
    for i in range(num_blocks):
        for j in range(i + 1, num_blocks):
            b1, b2 = blocks[i], blocks[j]
            # Ignore self-comparisons inside exact same line range
            if b1.file_path == b2.file_path and b1.start_line == b2.start_line:
                continue

            sim = jaccard_similarity(block_ngrams[i], block_ngrams[j])
            if sim >= similarity_threshold:
                p1 = str(Path(b1.file_path).resolve())
                p2 = str(Path(b2.file_path).resolve())
                commits1 = file_commits.get(p1, set())
                commits2 = file_commits.get(p2, set())
                shared_commits = len(commits1.intersection(commits2))

                # Check if content differs (if content is identical, no drift)
                if b1.content.strip() == b2.content.strip():
                    continue

                # Determine which block is newer based on file mtime
                mtime1 = get_file_last_mtime(b1.file_path)
                mtime2 = get_file_last_mtime(b2.file_path)

                updated, outdated = (b1, b2) if mtime1 >= mtime2 else (b2, b1)

                patch = generate_patch(updated, outdated)
                reports.append(
                    DriftReport(
                        updated_file=updated.file_path,
                        updated_range=f"{updated.start_line}-{updated.end_line}",
                        outdated_file=outdated.file_path,
                        outdated_range=f"{outdated.start_line}-{outdated.end_line}",
                        similarity=round(sim, 3),
                        historical_coupling_commits=shared_commits,
                        patch_suggestion=patch,
                    )
                )

    return reports


def format_text_report(reports: List[DriftReport]) -> str:
    """Format drift reports into terminal readable string."""
    if not reports:
        return "No copy drift detected across structural code blocks."

    lines = [
        f"=== Copy Drift Audit Report ({len(reports)} drift instances detected) ===",
        "",
    ]
    for r in reports:
        sim_pct = r.similarity * 100
        hc = r.historical_coupling_commits
        lines.append(
            f"Drift Similarity: {sim_pct:.1f}% | Historical Coupling: {hc} commits"
        )
        lines.append(f"  Updated Block:  {r.updated_file}:{r.updated_range}")
        lines.append(f"  Outdated Block: {r.outdated_file}:{r.outdated_range}")
        lines.append("  Patch Suggestion:")
        for line in r.patch_suggestion.splitlines():
            lines.append(f"    {line}")
        lines.append("-" * 60)
    return "\n".join(lines)


def main() -> None:
    """Main CLI entrypoint for copy-drift."""
    parser = argparse.ArgumentParser(
        description="Discover structurally similar code blocks and detect copy drift."
    )
    parser.add_argument(
        "path",
        nargs="?",
        default=".",
        help="Target directory or file path to analyze",
    )
    parser.add_argument(
        "--similarity-threshold",
        type=float,
        default=0.75,
        help="Similarity threshold between 0.0 and 1.0 (default: 0.75)",
    )
    parser.add_argument(
        "--min-lines",
        type=int,
        default=4,
        help="Minimum block size in lines (default: 4)",
    )
    parser.add_argument(
        "--format",
        choices=["text", "json"],
        default="text",
        help="Output format (default: text)",
    )

    args = parser.parse_args()
    target_path = Path(args.path).resolve()

    if not target_path.exists():
        print(f"Error: Target path '{target_path}' does not exist.", file=sys.stderr)
        sys.exit(1)

    if target_path.is_file():
        files = [target_path]
        repo_dir = target_path.parent
    else:
        files = list(target_path.rglob("*.py"))
        repo_dir = target_path

    blocks: List[CodeBlock] = []
    for f in files:
        blocks.extend(extract_blocks_from_file(f, min_lines=args.min_lines))

    file_commits = get_git_commit_history(repo_dir)
    drift_reports = detect_copy_drift(
        blocks,
        similarity_threshold=args.similarity_threshold,
        file_commits=file_commits,
    )

    if args.format == "json":
        print(json.dumps([asdict(r) for r in drift_reports], indent=2))
    else:
        print(format_text_report(drift_reports))

    sys.exit(0 if not drift_reports else 1)


if __name__ == "__main__":
    main()
