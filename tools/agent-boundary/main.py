"""Agent Boundary Tool.

Maintains a hunk-level provenance ledger for human vs AI coding agent edits to
report human-originated vs agent-originated lines, overwritten human edits,
and scope violations.
"""

# pylint: disable=too-many-branches,too-many-statements
# pylint: disable=too-many-locals,too-many-arguments,too-many-positional-arguments
# pylint: disable=too-many-instance-attributes

import argparse
import difflib
import fnmatch
import json
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Union


@dataclass
class LineProvenance:
    """Provenance entry for a single line in a file."""

    line_number: int
    content: str
    author_type: str  # 'HUMAN' or 'AGENT'
    author_name: str
    session_id: str


@dataclass
class FileProvenanceLedger:
    """Provenance ledger for a file across sessions."""

    file_path: str
    lines: List[LineProvenance] = field(default_factory=list)
    overwritten_human_lines: int = 0
    scope_violations: List[str] = field(default_factory=list)


@dataclass
class ContributionReport:
    """Summary of author contributions for a file or repository."""

    total_lines: int = 0
    human_lines: int = 0
    agent_lines: int = 0
    overwritten_human_lines: int = 0
    scope_violations: List[str] = field(default_factory=list)

    @property
    def human_percentage(self) -> float:
        """Percentage of human-authored lines."""
        return (
            round((self.human_lines / self.total_lines) * 100, 2)
            if self.total_lines > 0
            else 0.0
        )

    @property
    def agent_percentage(self) -> float:
        """Percentage of agent-authored lines."""
        return (
            round((self.agent_lines / self.total_lines) * 100, 2)
            if self.total_lines > 0
            else 0.0
        )


class ProvenanceTracker:
    """Tracks and records line-level provenance of code changes."""

    def __init__(self, ledger_file: Union[str, Path] = "provenance_ledger.json"):
        self.ledger_file = Path(ledger_file).resolve()
        self.ledger_data: Dict[str, FileProvenanceLedger] = self.load_ledger()

    def load_ledger(self) -> Dict[str, FileProvenanceLedger]:
        """Load ledger entries from disk."""
        if self.ledger_file.exists():
            try:
                raw = json.loads(self.ledger_file.read_text(encoding="utf-8"))
                res = {}
                for rel_path, data in raw.get("files", {}).items():
                    lines = [LineProvenance(**item) for item in data.get("lines", [])]
                    res[rel_path] = FileProvenanceLedger(
                        file_path=rel_path,
                        lines=lines,
                        overwritten_human_lines=data.get("overwritten_human_lines", 0),
                        scope_violations=data.get("scope_violations", []),
                    )
                return res
            except (OSError, ValueError, KeyError, json.JSONDecodeError):
                pass
        return {}

    def save_ledger(self) -> None:
        """Save ledger entries to disk."""
        raw_files = {}
        for rel_path, f_ledger in self.ledger_data.items():
            raw_files[rel_path] = {
                "file_path": f_ledger.file_path,
                "lines": [asdict(item) for item in f_ledger.lines],
                "overwritten_human_lines": f_ledger.overwritten_human_lines,
                "scope_violations": f_ledger.scope_violations,
            }
        content = {"files": raw_files}
        self.ledger_file.write_text(json.dumps(content, indent=2), encoding="utf-8")

    def record_edit_session(
        self,
        file_path: str,
        new_content: str,
        author_type: str,
        author_name: str,
        session_id: str = "session_001",
        allowed_scope_patterns: Optional[List[str]] = None,
    ) -> FileProvenanceLedger:
        """Record line provenance for a file update."""
        author_type = author_type.upper()
        if author_type not in ("HUMAN", "AGENT"):
            raise ValueError("author_type must be 'HUMAN' or 'AGENT'")

        rel_path = Path(file_path).as_posix()
        f_ledger = self.ledger_data.get(
            rel_path, FileProvenanceLedger(file_path=rel_path)
        )

        # Check scope violation
        if allowed_scope_patterns and author_type == "AGENT":
            in_scope = any(
                fnmatch.fnmatch(rel_path, pat)
                or fnmatch.fnmatch(Path(rel_path).name, pat)
                for pat in allowed_scope_patterns
            )
            if not in_scope:
                msg = (
                    f"Agent '{author_name}' modified file '{rel_path}' outside "
                    f"permitted scope {allowed_scope_patterns}."
                )
                f_ledger.scope_violations.append(msg)

        old_lines = [lp.content for lp in f_ledger.lines]
        new_line_texts = new_content.splitlines()

        matcher = difflib.SequenceMatcher(None, old_lines, new_line_texts)
        updated_provenance: List[LineProvenance] = []
        overwritten_count = 0

        for tag, i1, i2, j1, j2 in matcher.get_opcodes():
            if tag == "equal":
                # Keep existing provenance
                for idx in range(i1, i2):
                    old_p = f_ledger.lines[idx]
                    old_p.line_number = len(updated_provenance) + 1
                    updated_provenance.append(old_p)
            elif tag in ("replace", "delete"):
                # Count deleted human lines if agent is replacing/deleting
                if author_type == "AGENT":
                    for idx in range(i1, i2):
                        if f_ledger.lines[idx].author_type == "HUMAN":
                            overwritten_count += 1

                if tag == "replace":
                    for j in range(j1, j2):
                        updated_provenance.append(
                            LineProvenance(
                                line_number=len(updated_provenance) + 1,
                                content=new_line_texts[j],
                                author_type=author_type,
                                author_name=author_name,
                                session_id=session_id,
                            )
                        )
            elif tag == "insert":
                for j in range(j1, j2):
                    updated_provenance.append(
                        LineProvenance(
                            line_number=len(updated_provenance) + 1,
                            content=new_line_texts[j],
                            author_type=author_type,
                            author_name=author_name,
                            session_id=session_id,
                        )
                    )

        f_ledger.lines = updated_provenance
        f_ledger.overwritten_human_lines += overwritten_count
        self.ledger_data[rel_path] = f_ledger
        self.save_ledger()

        return f_ledger

    def generate_report(self) -> ContributionReport:
        """Generate repository-wide provenance report."""
        report = ContributionReport()

        for f_ledger in self.ledger_data.values():
            report.total_lines += len(f_ledger.lines)
            for line in f_ledger.lines:
                if line.author_type == "HUMAN":
                    report.human_lines += 1
                elif line.author_type == "AGENT":
                    report.agent_lines += 1

            report.overwritten_human_lines += f_ledger.overwritten_human_lines
            report.scope_violations.extend(f_ledger.scope_violations)

        return report


def build_parser() -> argparse.ArgumentParser:
    """Build CLI parser."""
    desc = "Maintain hunk-level provenance ledger for Human vs Agent code edits."
    parser = argparse.ArgumentParser(description=desc)
    subparsers = parser.add_subparsers(dest="command", help="Sub-command to run")

    record_parser = subparsers.add_parser(
        "record", help="Record edit session provenance"
    )
    record_parser.add_argument("--file", required=True, help="File path being updated")
    record_parser.add_argument(
        "--author-type",
        required=True,
        choices=["HUMAN", "AGENT"],
        help="Type of author",
    )
    record_parser.add_argument("--author-name", required=True, help="Author identifier")
    record_parser.add_argument(
        "--scope", nargs="*", help="Allowed scope patterns for AGENT"
    )
    record_parser.add_argument(
        "--ledger", default="provenance_ledger.json", help="Ledger file path"
    )

    report_parser = subparsers.add_parser("report", help="Generate contribution report")
    report_parser.add_argument(
        "--ledger", default="provenance_ledger.json", help="Ledger file path"
    )
    return parser


def main(args: Optional[List[str]] = None) -> int:
    """CLI entry point for agent-boundary."""
    parser = build_parser()
    parsed = parser.parse_args(args)

    if not parsed.command:
        parser.print_help()
        return 1

    tracker = ProvenanceTracker(ledger_file=parsed.ledger)

    if parsed.command == "record":
        fp = Path(parsed.file)
        if not fp.exists():
            print(f"Error: File '{parsed.file}' does not exist.")
            return 1

        content = fp.read_text(encoding="utf-8", errors="replace")
        f_ledger = tracker.record_edit_session(
            file_path=parsed.file,
            new_content=content,
            author_type=parsed.author_type,
            author_name=parsed.author_name,
            allowed_scope_patterns=parsed.scope,
        )

        msg = (
            f"Recorded edit session for '{parsed.file}' by "
            f"{parsed.author_type} ({parsed.author_name})."
        )
        print(msg)
        if f_ledger.scope_violations:
            print(f"[WARNING] Scope Violation: {f_ledger.scope_violations[-1]}")

    elif parsed.command == "report":
        rep = tracker.generate_report()
        print("=== Agent-Human Provenance & Boundary Report ===")
        print(f"Total Lines Tracked:     {rep.total_lines}")
        h_str = f"{rep.human_lines} ({rep.human_percentage}%)"
        a_str = f"{rep.agent_lines} ({rep.agent_percentage}%)"
        print(f"Human Originated Lines:  {h_str}")
        print(f"Agent Originated Lines:  {a_str}")
        print(f"Overwritten Human Lines: {rep.overwritten_human_lines}")

        if rep.scope_violations:
            print(f"\n[ALERTS] Scope Violations ({len(rep.scope_violations)}):")
            for v in rep.scope_violations:
                print(f"  ! {v}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
