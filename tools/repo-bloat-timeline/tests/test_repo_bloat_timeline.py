"""Unit tests for repo_bloat_timeline."""

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

# noqa: E402
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import pytest  # noqa: E402
from repo_bloat_timeline.main import (  # noqa: E402
    BloatFile,
    GitRunner,
    analyze_commit_bloat,
    find_repo_bloat_timeline,
    main,
    parse_commit_log,
    render_text_report,
)


def test_git_runner_success() -> None:
    """Test GitRunner executes git commands correctly."""
    with patch("shutil.which", return_value="/usr/bin/git"):
        with patch("subprocess.run") as mock_run:
            mock_run.return_value.stdout = "abc1234\n"
            runner = GitRunner(".")
            out = runner.run_git(["status"])
            assert out == "abc1234"


def test_git_runner_no_git() -> None:
    """Test GitRunner raises RuntimeError when git is missing."""
    with patch("shutil.which", return_value=None):
        runner = GitRunner(".")
        with pytest.raises(RuntimeError, match="Git executable not found"):
            runner.run_git(["status"])


def test_git_runner_error() -> None:
    """Test GitRunner raises RuntimeError on git command failure."""
    with patch("shutil.which", return_value="/usr/bin/git"):
        with patch("subprocess.run", side_effect=Exception("Git command error")):
            runner = GitRunner(".")
            with pytest.raises(RuntimeError):
                runner.run_git(["invalid"])


def test_parse_commit_log() -> None:
    """Test parsing commit log output."""
    runner = MagicMock()
    runner.run_git.return_value = (
        "hash1\x1fAuthor One\x1f2026-01-01T00:00:00Z\x1fCommit message 1\n"
        "hash2\x1fAuthor Two\x1f2026-01-02T00:00:00Z\x1fCommit message 2"
    )

    commits = parse_commit_log(runner, "HEAD", 10)
    assert len(commits) == 2
    assert commits[0]["hash"] == "hash1"
    assert commits[0]["author"] == "Author One"


def test_parse_commit_log_empty() -> None:
    """Test parse_commit_log with empty git log."""
    runner = MagicMock()
    runner.run_git.return_value = ""
    commits = parse_commit_log(runner, "HEAD", 10)
    assert commits == []


def test_analyze_commit_bloat() -> None:
    """Test analyzing text and binary file diffs in a commit."""
    runner = MagicMock()

    def mock_run_git(args: list) -> str:  # type: ignore[type-arg]
        if args[0] == "diff-tree":
            return "10\t5\tfile1.py\n-\t-\tbig_asset.bin"
        if args[0] == "cat-file":
            return "2097152"  # 2MB
        return ""

    runner.run_git.side_effect = mock_run_git

    net_bytes, large_files = analyze_commit_bloat(
        runner, "commit1", threshold_bytes=1048576
    )
    assert net_bytes > 2000000
    assert len(large_files) == 1
    assert large_files[0].path == "big_asset.bin"
    assert large_files[0].size_bytes == 2097152


def test_analyze_commit_bloat_cat_file_error() -> None:
    """Test handling cat-file failure gracefully."""
    runner = MagicMock()

    def mock_run_git(args: list) -> str:  # type: ignore[type-arg]
        if args[0] == "diff-tree":
            return "-\t-\tdeleted.bin"
        raise RuntimeError("Object not found")

    runner.run_git.side_effect = mock_run_git

    net_bytes, large_files = analyze_commit_bloat(
        runner, "commit1", threshold_bytes=100
    )
    assert net_bytes == 0
    assert large_files == []


def test_find_repo_bloat_timeline() -> None:
    """Test finding bloat timeline across multiple commits."""
    with patch("repo_bloat_timeline.main.GitRunner") as mock_runner_cls:
        mock_runner = MagicMock()
        mock_runner_cls.return_value = mock_runner

        with patch("repo_bloat_timeline.main.parse_commit_log") as mock_parse:
            mock_parse.return_value = [
                {
                    "hash": "c1",
                    "author": "Alice",
                    "date": "2026-01-01",
                    "subject": "Add asset",
                }
            ]
            with patch("repo_bloat_timeline.main.analyze_commit_bloat") as mock_analyze:
                mock_analyze.return_value = (
                    3000000,
                    [BloatFile("data.bin", 3000000, "added")],
                )

                res = find_repo_bloat_timeline(repo_path=".", threshold_mb=1.0, top_n=5)
                assert res["commits_scanned"] == 1
                assert res["bloat_commits_found"] == 1
                assert len(res["top_bloat_commits"]) == 1


def test_render_text_report() -> None:
    """Test text report formatting."""
    report = {
        "repository": "/path/to/repo",
        "commits_scanned": 100,
        "bloat_commits_found": 1,
        "threshold_mb": 1.0,
        "top_bloat_commits": [
            {
                "commit_hash": "c1234567890",
                "author": "Bob",
                "date": "2026-01-01T12:00:00",
                "subject": "Big commit",
                "net_bytes_added": 5242880,
                "large_files": [
                    {
                        "path": "video.mp4",
                        "size_bytes": 5242880,
                        "action": "added",
                    }
                ],
            }
        ],
    }
    output = render_text_report(report)
    assert "Repo Bloat Timeline Report" in output
    assert "Bob" in output
    assert "video.mp4" in output


def test_render_text_report_empty() -> None:
    """Test text report formatting when no bloat commits found."""
    report = {
        "repository": "/path/to/repo",
        "commits_scanned": 10,
        "bloat_commits_found": 0,
        "threshold_mb": 1.0,
        "top_bloat_commits": [],
    }
    output = render_text_report(report)
    assert "No commits exceeded the bloat threshold." in output


def test_cli_main_text(capsys: pytest.CaptureFixture[str]) -> None:
    """Test CLI main function with text output."""
    with patch("sys.argv", ["repo-bloat-timeline", "--repo", ".", "--format", "text"]):
        with patch("repo_bloat_timeline.main.find_repo_bloat_timeline") as mock_find:
            mock_find.return_value = {
                "repository": ".",
                "commits_scanned": 5,
                "bloat_commits_found": 0,
                "threshold_mb": 1.0,
                "top_bloat_commits": [],
            }
            main()
            captured = capsys.readouterr()
            assert "Repo Bloat Timeline Report" in captured.out


def test_cli_main_json(capsys: pytest.CaptureFixture[str]) -> None:
    """Test CLI main function with json output."""
    with patch(
        "sys.argv",
        ["repo-bloat-timeline", "--repo", ".", "--format", "json", "-v"],
    ):
        with patch("repo_bloat_timeline.main.find_repo_bloat_timeline") as mock_find:
            mock_find.return_value = {"status": "ok"}
            main()
            captured = capsys.readouterr()
            parsed = json.loads(captured.out)
            assert parsed["status"] == "ok"


def test_cli_main_error() -> None:
    """Test CLI main function exiting on error."""
    with patch("sys.argv", ["repo-bloat-timeline", "--repo", "/nonexistent"]):
        with patch(
            "repo_bloat_timeline.main.find_repo_bloat_timeline",
            side_effect=RuntimeError("Invalid repo"),
        ):
            with pytest.raises(SystemExit) as exc:
                main()
            assert exc.value.code == 1
