"""Tests for git_cleanup.py."""

import os
import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from git_cleanup import (
    LargeFile,
    StaleBranch,
    SecretFinding,
    CleanupReport,
    shannon_entropy,
    find_large_files,
    scan_commits_for_secrets,
)


# ---------------------------------------------------------------------------
# shannon_entropy
# ---------------------------------------------------------------------------
class TestShannonEntropy:
    def test_empty_string(self) -> None:
        assert shannon_entropy("") == 0.0

    def test_uniform_string(self) -> None:
        # All same chars → entropy 0
        assert shannon_entropy("aaaa") == 0.0

    def test_two_chars(self) -> None:
        val = shannon_entropy("abababab")
        assert abs(val - 1.0) < 1e-6

    def test_high_entropy(self) -> None:
        # Random-looking base64 → should be > 4.0
        val = shannon_entropy("A3kP9zXmQ7rLnBvWsTuYoHjEiCdFgN2p")
        assert val > 4.0

    def test_low_entropy_repeated(self) -> None:
        val = shannon_entropy("aaaaabbbbb")
        assert val < 2.0


# ---------------------------------------------------------------------------
# find_large_files
# ---------------------------------------------------------------------------
class TestFindLargeFiles:
    def test_finds_large_file(self, tmp_path: Path) -> None:
        # Initialize a bare git repo
        subprocess.run(["git", "init"], cwd=str(tmp_path), capture_output=True)
        subprocess.run(
            ["git", "config", "user.email", "test@test.com"],
            cwd=str(tmp_path), capture_output=True
        )
        subprocess.run(
            ["git", "config", "user.name", "Test"],
            cwd=str(tmp_path), capture_output=True
        )
        # Create a large file (600 KB)
        big = tmp_path / "big.bin"
        big.write_bytes(b"x" * 600 * 1024)
        subprocess.run(["git", "add", "."], cwd=str(tmp_path), capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "init"],
            cwd=str(tmp_path), capture_output=True
        )

        results = find_large_files(str(tmp_path), 500)
        paths = [r.path for r in results]
        assert "big.bin" in paths

    def test_small_file_not_included(self, tmp_path: Path) -> None:
        subprocess.run(["git", "init"], cwd=str(tmp_path), capture_output=True)
        subprocess.run(
            ["git", "config", "user.email", "test@test.com"],
            cwd=str(tmp_path), capture_output=True
        )
        subprocess.run(
            ["git", "config", "user.name", "Test"],
            cwd=str(tmp_path), capture_output=True
        )
        small = tmp_path / "small.txt"
        small.write_text("hello")
        subprocess.run(["git", "add", "."], cwd=str(tmp_path), capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "init"],
            cwd=str(tmp_path), capture_output=True
        )

        results = find_large_files(str(tmp_path), 500)
        assert results == []


# ---------------------------------------------------------------------------
# scan_commits_for_secrets (pattern matching)
# ---------------------------------------------------------------------------
class TestScanCommitsForSecrets:
    def test_detects_aws_key_in_commit(self, tmp_path: Path) -> None:
        subprocess.run(["git", "init"], cwd=str(tmp_path), capture_output=True)
        subprocess.run(
            ["git", "config", "user.email", "t@t.com"],
            cwd=str(tmp_path), capture_output=True
        )
        subprocess.run(
            ["git", "config", "user.name", "T"],
            cwd=str(tmp_path), capture_output=True
        )
        secret_file = tmp_path / "config.py"
        secret_file.write_text('AWS_KEY = "AKIAIOSFODNN7EXAMPLE"\n')
        subprocess.run(["git", "add", "."], cwd=str(tmp_path), capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "add config"],
            cwd=str(tmp_path), capture_output=True
        )

        findings = scan_commits_for_secrets(str(tmp_path), max_commits=10, entropy_threshold=4.5)
        pattern_names = [f.pattern_name for f in findings]
        assert "AWS Access Key" in pattern_names

    def test_no_findings_in_clean_repo(self, tmp_path: Path) -> None:
        subprocess.run(["git", "init"], cwd=str(tmp_path), capture_output=True)
        subprocess.run(
            ["git", "config", "user.email", "t@t.com"],
            cwd=str(tmp_path), capture_output=True
        )
        subprocess.run(
            ["git", "config", "user.name", "T"],
            cwd=str(tmp_path), capture_output=True
        )
        clean = tmp_path / "readme.md"
        clean.write_text("# Hello World\nThis is a clean file.\n")
        subprocess.run(["git", "add", "."], cwd=str(tmp_path), capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "init"],
            cwd=str(tmp_path), capture_output=True
        )

        findings = scan_commits_for_secrets(str(tmp_path), max_commits=10, entropy_threshold=4.5)
        # Filter out high-entropy false positives from normal text
        secret_findings = [f for f in findings if f.pattern_name != "High-Entropy Token"]
        assert secret_findings == []
