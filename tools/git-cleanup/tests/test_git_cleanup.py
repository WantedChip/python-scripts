"""Tests for git_cleanup.py."""

# pylint: disable=wrong-import-position,import-error,missing-class-docstring
# pylint: disable=missing-function-docstring,subprocess-run-check
import os
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from git_cleanup import (  # noqa: E402
    find_large_files,
    find_stale_branches,
    find_untracked_and_ignored,
    run_git,
    scan_commits_for_secrets,
    shannon_entropy,
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
            cwd=str(tmp_path),
            capture_output=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "Test"],
            cwd=str(tmp_path),
            capture_output=True,
        )
        # Create a large file (600 KB)
        big = tmp_path / "big.bin"
        big.write_bytes(b"x" * 600 * 1024)
        subprocess.run(["git", "add", "."], cwd=str(tmp_path), capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "init"], cwd=str(tmp_path), capture_output=True
        )

        results = find_large_files(str(tmp_path), 500)
        paths = [r.path for r in results]
        assert "big.bin" in paths

    def test_small_file_not_included(self, tmp_path: Path) -> None:
        subprocess.run(["git", "init"], cwd=str(tmp_path), capture_output=True)
        subprocess.run(
            ["git", "config", "user.email", "test@test.com"],
            cwd=str(tmp_path),
            capture_output=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "Test"],
            cwd=str(tmp_path),
            capture_output=True,
        )
        small = tmp_path / "small.txt"
        small.write_text("hello")
        subprocess.run(["git", "add", "."], cwd=str(tmp_path), capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "init"], cwd=str(tmp_path), capture_output=True
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
            cwd=str(tmp_path),
            capture_output=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "T"], cwd=str(tmp_path), capture_output=True
        )
        secret_file = tmp_path / "config.py"
        secret_file.write_text('AWS_KEY = "AKIAIOSFODNN7EXAMPLE"\n')
        subprocess.run(["git", "add", "."], cwd=str(tmp_path), capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "add config"],
            cwd=str(tmp_path),
            capture_output=True,
        )

        findings = scan_commits_for_secrets(
            str(tmp_path), max_commits=10, entropy_threshold=4.5
        )
        pattern_names = [f.pattern_name for f in findings]
        assert "AWS Access Key" in pattern_names

    def test_no_findings_in_clean_repo(self, tmp_path: Path) -> None:
        subprocess.run(["git", "init"], cwd=str(tmp_path), capture_output=True)
        subprocess.run(
            ["git", "config", "user.email", "t@t.com"],
            cwd=str(tmp_path),
            capture_output=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "T"], cwd=str(tmp_path), capture_output=True
        )
        clean = tmp_path / "readme.md"
        clean.write_text("# Hello World\nThis is a clean file.\n")
        subprocess.run(["git", "add", "."], cwd=str(tmp_path), capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "init"], cwd=str(tmp_path), capture_output=True
        )

        findings = scan_commits_for_secrets(
            str(tmp_path), max_commits=10, entropy_threshold=4.5
        )
        # Filter out high-entropy false positives from normal text
        secret_findings = [
            f for f in findings if f.pattern_name != "High-Entropy Token"
        ]
        assert secret_findings == []


def test_run_git_failure(tmp_path: Path) -> None:
    """Test run_git with invalid git command raising SystemExit."""
    with pytest.raises(SystemExit):
        run_git(["invalidcmd"], str(tmp_path))


def test_find_stale_branches_and_untracked(tmp_path: Path) -> None:
    """Test branch staleness and untracked file scanners in a live git repo."""
    # 1. Initialize git repo
    subprocess.run(["git", "init"], cwd=str(tmp_path), capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "test@test.com"],
        cwd=str(tmp_path),
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test"], cwd=str(tmp_path), capture_output=True
    )

    # 2. Add an initial commit on master
    f = tmp_path / "readme.txt"
    f.write_text("Hello")
    subprocess.run(["git", "add", "."], cwd=str(tmp_path), capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "initial commit"],
        cwd=str(tmp_path),
        capture_output=True,
    )

    # 3. Create a stale branch (inactive/merged)
    subprocess.run(
        ["git", "checkout", "-b", "feature/merged"],
        cwd=str(tmp_path),
        capture_output=True,
    )
    f2 = tmp_path / "feature.txt"
    f2.write_text("Feature")
    subprocess.run(["git", "add", "."], cwd=str(tmp_path), capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "feature commit"],
        cwd=str(tmp_path),
        capture_output=True,
    )

    # Merge it back to master
    subprocess.run(
        ["git", "checkout", "master"], cwd=str(tmp_path), capture_output=True
    )
    subprocess.run(
        ["git", "merge", "feature/merged"], cwd=str(tmp_path), capture_output=True
    )

    # 4. Check branches
    stale_branches = find_stale_branches(str(tmp_path), stale_days=30)
    # feature/merged should be found because it is merged into HEAD
    names = [b.name for b in stale_branches]
    assert "feature/merged" in names

    # 5. Check untracked and ignored
    untracked_file = tmp_path / "untracked.log"
    untracked_file.write_text("log")

    # Create an ignored file
    git_ignore = tmp_path / ".gitignore"
    git_ignore.write_text("*.ignored\n")
    subprocess.run(["git", "add", ".gitignore"], cwd=str(tmp_path), capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "add gitignore"], cwd=str(tmp_path), capture_output=True
    )

    ignored_file = tmp_path / "file.ignored"
    ignored_file.write_text("ignored")

    untracked, ignored = find_untracked_and_ignored(str(tmp_path))
    assert "untracked.log" in untracked
    # Depending on platform path separators
    ignored_names = [os.path.basename(i) for i in ignored]
    assert "file.ignored" in ignored_names


def test_main_cli_execution(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Test main execution with various arguments."""
    import git_cleanup

    # 1. Non-existent path exits 1
    with pytest.raises(SystemExit) as exc_info:
        git_cleanup.main(["--repo", "nonexistent_path_123_abc"])
    assert exc_info.value.code == 1

    # 2. Live repo execution check
    # Initialize a dummy git repo so it doesn't fail basic checks
    subprocess.run(["git", "init"], cwd=str(tmp_path), capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "test@test.com"],
        cwd=str(tmp_path),
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test"], cwd=str(tmp_path), capture_output=True
    )

    # Add a commit
    f = tmp_path / "init.txt"
    f.touch()
    subprocess.run(["git", "add", "."], cwd=str(tmp_path), capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "init"], cwd=str(tmp_path), capture_output=True
    )

    git_cleanup.main(["--repo", str(tmp_path)])
    captured = capsys.readouterr()
    assert "Git Repo Cleanup Report" in captured.out
    assert "Stale Branches" in captured.out
