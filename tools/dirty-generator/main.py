"""Dirty Generator Tool.

Profiles developer commands (e.g. npm test, pytest) by filesystem side effects
and detects baseline violations.
"""

# pylint: disable=too-many-branches,too-many-statements
# pylint: disable=too-many-locals,too-many-arguments,too-many-positional-arguments
# pylint: disable=too-many-instance-attributes,too-few-public-methods

import argparse
import fnmatch
import hashlib
import json
import os
import subprocess  # nosec B404
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Union


@dataclass
class FileState:
    """Snapshot state of a file."""

    path: str
    mtime: float
    size: int
    hash_val: str


@dataclass
class MutationReport:
    """Report of filesystem mutations caused by a command execution."""

    command: str
    execution_time_seconds: float
    created_files: List[str] = field(default_factory=list)
    modified_files: List[str] = field(default_factory=list)
    deleted_files: List[str] = field(default_factory=list)
    violations: List[str] = field(default_factory=list)

    @property
    def is_dirty(self) -> bool:
        """Check if any file changes occurred."""
        return (
            len(self.created_files) > 0
            or len(self.modified_files) > 0
            or len(self.deleted_files) > 0
        )


class CommandProfiler:
    """Snapshots filesystem state to track mutations."""

    def __init__(
        self,
        root_dir: Union[str, Path],
        baseline_path: Optional[Union[str, Path]] = None,
    ):
        self.root_dir = Path(root_dir).resolve()
        self.baseline_path = Path(baseline_path).resolve() if baseline_path else None
        self.baselines: Dict[str, List[str]] = self.load_baselines()

    def load_baselines(self) -> Dict[str, List[str]]:
        """Load allowed mutation baselines from file if exists."""
        if self.baseline_path and self.baseline_path.exists():
            try:
                data = json.loads(self.baseline_path.read_text(encoding="utf-8"))
                cmds = data.get("commands", {})
                if isinstance(cmds, dict):
                    return {str(k): list(v) for k, v in cmds.items()}
            except (OSError, ValueError, json.JSONDecodeError):
                pass
        return {}

    def save_baselines(self) -> None:
        """Save current baselines to baseline file."""
        if self.baseline_path:
            content = {"commands": self.baselines}
            self.baseline_path.write_text(
                json.dumps(content, indent=2), encoding="utf-8"
            )

    def compute_file_hash(self, filepath: Path) -> str:
        """Compute SHA256 snippet hash of file content."""
        try:
            hasher = hashlib.sha256()
            with open(filepath, "rb") as f:
                chunk = f.read(65536)
                while chunk:
                    hasher.update(chunk)
                    chunk = f.read(65536)
            return hasher.hexdigest()
        except OSError:
            return ""

    def snapshot(self) -> Dict[str, FileState]:
        """Take a snapshot of files under root_dir."""
        states: Dict[str, FileState] = {}
        for root, _, files in os.walk(self.root_dir):
            for file in files:
                full_path = Path(root) / file
                rel = full_path.relative_to(self.root_dir).as_posix()
                try:
                    stat = full_path.stat()
                    h = self.compute_file_hash(full_path)
                    states[rel] = FileState(
                        path=rel,
                        mtime=stat.st_mtime,
                        size=stat.st_size,
                        hash_val=h,
                    )
                except OSError:
                    pass
        return states

    def is_pattern_matched(self, path: str, patterns: List[str]) -> bool:
        """Check if path matches any pattern in allowed patterns."""
        for pattern in patterns:
            if fnmatch.fnmatch(path, pattern) or fnmatch.fnmatch(
                Path(path).name, pattern
            ):
                return True
        return False

    def profile_command(
        self, command: str, record_as_baseline: bool = False
    ) -> MutationReport:
        """Run command and detect filesystem side effects."""
        before_state = self.snapshot()

        start_time = time.time()
        res = subprocess.run(  # nosec B602, B603
            command,
            shell=True,
            cwd=str(self.root_dir),
            capture_output=True,
            text=True,
            check=False,
        )
        _ = res
        elapsed = time.time() - start_time

        after_state = self.snapshot()

        created: List[str] = []
        modified: List[str] = []
        deleted: List[str] = []

        for path, state in after_state.items():
            if path not in before_state:
                created.append(path)
            elif (
                state.size != before_state[path].size
                or state.hash_val != before_state[path].hash_val
            ):
                modified.append(path)

        for path in before_state:
            if path not in after_state:
                deleted.append(path)

        report = MutationReport(
            command=command,
            execution_time_seconds=round(elapsed, 3),
            created_files=sorted(created),
            modified_files=sorted(modified),
            deleted_files=sorted(deleted),
        )

        allowed_patterns = self.baselines.get(command, [])

        # Check violations against allowed baselines
        for path in created + modified + deleted:
            if not self.is_pattern_matched(path, allowed_patterns):
                report.violations.append(path)

        if record_as_baseline:
            mutations = sorted(list(set(created + modified + deleted)))
            self.baselines[command] = mutations
            self.save_baselines()

        return report


def build_parser() -> argparse.ArgumentParser:
    """Build CLI parser."""
    desc = "Profile developer command side effects and detect baseline " + "violations."
    parser = argparse.ArgumentParser(description=desc)
    parser.add_argument("--cmd", required=True, help="Command string to execute")
    parser.add_argument(
        "--root", default=".", help="Root directory to monitor for mutations"
    )
    parser.add_argument(
        "--baseline-file", help="Path to JSON file storing baseline mutations"
    )
    parser.add_argument(
        "--record-baseline",
        action="store_true",
        help="Record mutations of this run as baseline",
    )
    return parser


def main(args: Optional[List[str]] = None) -> int:
    """CLI Entry point."""
    parser = build_parser()
    parsed = parser.parse_args(args)

    profiler = CommandProfiler(root_dir=parsed.root, baseline_path=parsed.baseline_file)
    report = profiler.profile_command(
        command=parsed.cmd, record_as_baseline=parsed.record_baseline
    )

    print("=== Command Side-Effect Profile Report ===")
    print(f"Command:        {report.command}")
    print(f"Execution Time: {report.execution_time_seconds}s")
    print(f"Filesystem Dirty: {report.is_dirty}\n")

    print(f"Created Files ({len(report.created_files)}):")
    for f in report.created_files:
        print(f"  + {f}")

    print(f"Modified Files ({len(report.modified_files)}):")
    for f in report.modified_files:
        print(f"  ~ {f}")

    print(f"Deleted Files ({len(report.deleted_files)}):")
    for f in report.deleted_files:
        print(f"  - {f}")

    if report.violations:
        msg = f"\n[ALERT] Baseline Violations ({len(report.violations)}):"
        print(msg)
        for v in report.violations:
            print(f"  ! {v}")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
