"""Repository Documentation Auditor — audit repo documentation health."""

import argparse
import ast
import json
import logging
import re
import sys
from pathlib import Path
from typing import Dict, List, Optional, Set

# Regex to find links in Markdown: [Text](URL/Path)
MARKDOWN_LINK_RE = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")

# Regex to find headers in Markdown (e.g. # Header Name)
MARKDOWN_HEADER_RE = re.compile(r"^(#{1,6})\s+(.+)$")


def slugify(text: str) -> str:
    """Convert header text to standard GitHub markdown anchor slug."""
    s = text.lower().strip()
    # Remove standard punctuation/formatting characters except hyphens and alphanumeric
    s = re.sub(r"[^\w\s\-]", "", s)
    s = re.sub(r"[\s\_]+", "-", s)
    return s


def get_str_val(node: ast.AST) -> Optional[str]:
    """Helper to extract string literal values in AST across Python versions."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    # Fallback for Python versions before Constant unification
    if hasattr(ast, "Str") and isinstance(node, getattr(ast, "Str")):
        val = getattr(node, "s")
        if isinstance(val, str):
            return val
    return None


class EnvVarVisitor(ast.NodeVisitor):
    """AST visitor to find environment variables referenced in Python code."""

    def __init__(self) -> None:
        self.env_vars: Set[str] = set()

    def visit_Call(self, node: ast.Call) -> None:  # pylint: disable=invalid-name
        """Inspect calls to os.getenv or os.environ.get."""
        func = node.func
        # os.getenv(...)
        if isinstance(func, ast.Attribute):
            if (
                isinstance(func.value, ast.Name)
                and func.value.id == "os"
                and func.attr == "getenv"
            ):
                if node.args:
                    val = get_str_val(node.args[0])
                    if val:
                        self.env_vars.add(val)
            # os.environ.get(...)
            elif (
                isinstance(func.value, ast.Attribute)
                and isinstance(func.value.value, ast.Name)
                and func.value.value.id == "os"
                and func.value.attr == "environ"
                and func.attr == "get"
            ):
                if node.args:
                    val = get_str_val(node.args[0])
                    if val:
                        self.env_vars.add(val)
        # getenv(...) imported directly
        elif isinstance(func, ast.Name) and func.id == "getenv":
            if node.args:
                val = get_str_val(node.args[0])
                if val:
                    self.env_vars.add(val)

        self.generic_visit(node)

    # pylint: disable=invalid-name
    def visit_Subscript(self, node: ast.Subscript) -> None:
        """Inspect access like os.environ['VAR']."""
        val_node = node.value
        # os.environ[...]
        if isinstance(val_node, ast.Attribute):
            if (
                isinstance(val_node.value, ast.Name)
                and val_node.value.id == "os"
                and val_node.attr == "environ"
            ):
                val = get_str_val(node.slice)
                if val:
                    self.env_vars.add(val)

        self.generic_visit(node)


class DocAuditor:
    """Audits repository documentation files for errors/omissions."""

    def __init__(self, root_dir: Path, exclude_patterns: List[str]) -> None:
        self.root_dir = root_dir.resolve()
        self.exclude_patterns = exclude_patterns + [
            "venv",
            ".venv",
            ".git",
            "node_modules",
            "__pycache__",
            ".mypy_cache",
            ".pytest_cache",
            ".agents",
        ]
        self.issues: List[Dict[str, str]] = []

    def should_exclude(self, path: Path) -> bool:
        """Check if path matches any excluded directory/file pattern."""
        rel = path.relative_to(self.root_dir)
        parts = rel.parts
        for part in parts:
            if part in self.exclude_patterns:
                return True
        return False

    def add_issue(self, category: str, file: str, description: str) -> None:
        """Record an audit issue."""
        self.issues.append(
            {
                "category": category,
                "file": file,
                "description": description,
            }
        )

    def audit_setup_instructions(self) -> None:
        """Audit root README for setup and installation instructions."""
        readme = self.root_dir / "README.md"
        if not readme.is_file():
            self.add_issue(
                "setup",
                "README.md",
                "Repository is missing root README.md file.",
            )
            return

        try:
            content = readme.read_text(encoding="utf-8")
        except OSError as e:
            self.add_issue("setup", "README.md", f"Failed to read README: {e}")
            return

        # Check headers
        headers = ["installation", "setup", "quick start", "getting started", "usage"]
        has_setup_header = False
        for line in content.splitlines():
            match = MARKDOWN_HEADER_RE.match(line)
            if match:
                header_text = match.group(2).lower()
                if any(h in header_text for h in headers):
                    has_setup_header = True
                    break

        if not has_setup_header:
            self.add_issue(
                "setup",
                "README.md",
                "README.md lacks Setup/Installation/Usage instruction headers.",
            )

        # Cross-reference dependency files
        dep_files = {
            "requirements.txt": "requirements.txt",
            "pyproject.toml": "pyproject.toml",
            "setup.py": "setup.py",
        }
        for filename, term in dep_files.items():
            if (self.root_dir / filename).is_file():
                if term not in content:
                    self.add_issue(
                        "setup",
                        "README.md",
                        f"Repository contains {filename} but "
                        "it is not mentioned in README.md.",
                    )

    def audit_dead_commands(self) -> None:
        """Scan all markdown files for dead run commands referencing missing scripts."""
        for path in self.root_dir.rglob("*.md"):
            if self.should_exclude(path):
                continue

            try:
                content = path.read_text(encoding="utf-8")
            except OSError:
                continue

            # Find markdown code blocks
            # Look for lines running files locally: e.g. python path/to/script.py
            pattern = re.compile(r"(?:python|python3)\s+([a-zA-Z0-9_\-\./\\]+\.py)")
            for m in pattern.finditer(content):
                script_ref = m.group(1).replace("\\", "/")
                # Determine path relative to root or relative to markdown file
                p1 = self.root_dir / script_ref
                p2 = path.parent / script_ref
                if not p1.is_file() and not p2.is_file():
                    self.add_issue(
                        "dead_command",
                        str(path.relative_to(self.root_dir)),
                        f"README references non-existent script: {script_ref}",
                    )

    def audit_undocumented_env_vars(self) -> None:
        """Extract env vars from Python code and check if they are documented."""
        # 1. Extract from all Python files
        code_env_vars: Set[str] = set()
        for path in self.root_dir.rglob("*.py"):
            if self.should_exclude(path):
                continue

            try:
                content = path.read_text(encoding="utf-8")
                tree = ast.parse(content, filename=str(path))
                visitor = EnvVarVisitor()
                visitor.visit(tree)
                code_env_vars.update(visitor.env_vars)
            except (SyntaxError, OSError):
                continue

        if not code_env_vars:
            return

        # 2. Gather documentation content
        doc_content = ""
        # Read all Markdown files
        for path in self.root_dir.rglob("*.md"):
            if self.should_exclude(path):
                continue
            try:
                doc_content += path.read_text(encoding="utf-8") + "\n"
            except OSError:
                continue

        # Also read .env.example if exists
        env_ex = self.root_dir / ".env.example"
        if env_ex.is_file():
            try:
                doc_content += env_ex.read_text(encoding="utf-8") + "\n"
            except OSError:
                pass

        # 3. Check documentation
        for var in code_env_vars:
            if var not in doc_content:
                self.add_issue(
                    "undocumented_env",
                    "Multiple Files",
                    f"Environment variable '{var}' is used in code but undocumented.",
                )

    def _check_link(
        self, path: Path, link_text: str, link_url: str, headers: Set[str]
    ) -> None:
        """Helper to audit a single markdown link."""
        if (
            link_url.startswith("http://")
            or link_url.startswith("https://")
            or link_url.startswith("mailto:")
            or link_url.startswith("ftp://")
        ):
            return

        # Case 1: Internal anchor link e.g. #installation
        if link_url.startswith("#"):
            anchor = link_url[1:]
            if anchor not in headers:
                self.add_issue(
                    "stale_anchor",
                    str(path.relative_to(self.root_dir)),
                    f"Broken internal link [{link_text}]({link_url}). "
                    "Anchor does not exist.",
                )
            return

        # Case 2: Local file path
        clean_url = link_url.split("#")[0]
        if not clean_url:
            return

        clean_url = clean_url.replace("%20", " ")

        target_path = (path.parent / clean_url).resolve()
        if not target_path.exists():
            alt_target = (self.root_dir / clean_url.lstrip("/")).resolve()
            if not alt_target.exists():
                self.add_issue(
                    "broken_path",
                    str(path.relative_to(self.root_dir)),
                    f"Broken file link [{link_text}]({link_url}). "
                    "File does not exist.",
                )

    def audit_stale_references(self) -> None:
        """Scan markdown files for dead internal anchors and broken local
        file references.
        """
        for path in self.root_dir.rglob("*.md"):
            if self.should_exclude(path):
                continue

            try:
                content = path.read_text(encoding="utf-8")
            except OSError:
                continue

            # Collect valid header anchors in this file
            headers: Set[str] = set()
            for line in content.splitlines():
                m_hdr = MARKDOWN_HEADER_RE.match(line)
                if m_hdr:
                    headers.add(slugify(m_hdr.group(2)))

            # Find all links
            for m_link in MARKDOWN_LINK_RE.finditer(content):
                self._check_link(
                    path,
                    m_link.group(1),
                    m_link.group(2).strip(),
                    headers,
                )

    def run_all(self) -> List[Dict[str, str]]:
        """Run all repository audits."""
        self.audit_setup_instructions()
        self.audit_dead_commands()
        self.audit_undocumented_env_vars()
        self.audit_stale_references()
        return self.issues


def main() -> None:
    """CLI execution entrypoint."""
    parser = argparse.ArgumentParser(
        description="Repository Documentation Auditor — audit documentation issues."
    )
    parser.add_argument(
        "repo_path",
        type=str,
        nargs="?",
        default=".",
        help="Path to repository root (defaults to current directory).",
    )
    parser.add_argument(
        "-e",
        "--exclude",
        type=str,
        default="",
        help="Comma-separated folder patterns to exclude.",
    )
    parser.add_argument(
        "--fail-on-warnings",
        action="store_true",
        help="Exit with non-zero code if issues are found.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output audit issues report in JSON format.",
    )

    args = parser.parse_args()

    repo_dir = Path(args.repo_path)
    if not repo_dir.is_dir():
        logger_name = "repository_documentation_auditor"
        logging.getLogger(logger_name).error(
            "Invalid repository directory: %s", repo_dir
        )
        sys.exit(2)

    excludes = [p.strip() for p in args.exclude.split(",") if p.strip()]

    auditor = DocAuditor(repo_dir, excludes)
    issues = auditor.run_all()

    if args.json:
        json.dump(issues, sys.stdout, indent=2, ensure_ascii=False)
    else:
        if not issues:
            print("Audit completed successfully. No documentation issues detected!")
        else:
            print(
                f"Auditor detected {len(issues)} issues "
                "in repository documentation:\n"
            )
            print(f"{'Category':<18} | {'File':<30} | {'Description'}")
            print("-" * 80)
            for issue in issues:
                file_short = issue["file"]
                if len(file_short) > 30:
                    file_short = "..." + file_short[-27:]
                print(
                    f"{issue['category']:<18} | "
                    f"{file_short:<30} | "
                    f"{issue['description']}"
                )

    if issues and args.fail_on_warnings:
        sys.exit(1)


if __name__ == "__main__":
    main()
