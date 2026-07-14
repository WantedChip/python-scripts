"""Unit tests for system_change_tracker.py."""

import json

# Add import injection to resolve checkers package
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# pylint: disable=import-error, wrong-import-position
import system_change_tracker  # noqa: E402


def test_calculate_file_hash(tmp_path: Path) -> None:
    """Test calculating file hashes."""
    f = tmp_path / "test.txt"
    f.write_text("hello world")
    h1 = system_change_tracker.calculate_file_hash(f)
    assert len(h1) == 64  # SHA-256 length

    # Error case
    assert (
        system_change_tracker.calculate_file_hash(Path("nonexistent"))
        == "error_reading_file"
    )


def test_snapshot_files(tmp_path: Path) -> None:
    """Test directory structure snapshotting."""
    f1 = tmp_path / "f1.txt"
    f1.write_text("aaa")
    d1 = tmp_path / "sub"
    d1.mkdir()
    f2 = d1 / "f2.txt"
    f2.write_text("bbbb")

    snap = system_change_tracker.snapshot_files([str(tmp_path)])
    assert f1.as_posix() in snap
    assert f2.as_posix() in snap
    assert snap[f1.as_posix()]["size"] == 3
    assert snap[f2.as_posix()]["size"] == 4


def test_get_python_packages() -> None:
    """Test collecting Python package distribution metadata."""
    pkgs = system_change_tracker.get_python_packages()
    assert isinstance(pkgs, dict)
    # Check if pytest is found (since it's installed in the venv)
    assert "pytest" in pkgs or len(pkgs) > 0


@patch("subprocess.run")
def test_get_linux_packages(mock_run: MagicMock) -> None:
    """Test parsing Linux packages."""
    mock_run.return_value = MagicMock(
        stdout="curl 7.81.0-1ubuntu1.16\npython3 3.10.6-1~22.04\n",
        returncode=0,
    )
    pkgs = system_change_tracker.get_linux_packages()
    assert pkgs.get("curl") == "7.81.0-1ubuntu1.16"
    assert pkgs.get("python3") == "3.10.6-1~22.04"


@patch("subprocess.run")
def test_get_windows_services(mock_run: MagicMock) -> None:
    """Test Windows services parser with mock sc query output."""
    sc_output = """
SERVICE_NAME: wuauserv
DISPLAY_NAME: Windows Update
        TYPE               : 20  WIN32_SHARE_PROCESS
        STATE              : 4  RUNNING
                                (STOPPABLE, NOT_PAUSABLE, ACCEPTS_PRESHUTDOWN)
        WIN32_EXIT_CODE    : 0  (0x0)
        SERVICE_EXIT_CODE  : 0  (0x0)
        CHECKPOINT         : 0x0
        WAIT_HINT          : 0x0
"""
    mock_run.return_value = MagicMock(stdout=sc_output, returncode=0)
    svcs = system_change_tracker.get_windows_services()
    assert svcs.get("wuauserv") == "RUNNING"


@patch("subprocess.run")
def test_get_linux_services(mock_run: MagicMock) -> None:
    """Test Linux services parser with mock systemctl output."""
    systemctl_output = (
        "  ssh.service                          loaded active running   SSH server\n"
        "  cron.service                         loaded active running   cron daemon\n"
    )
    mock_run.return_value = MagicMock(stdout=systemctl_output, returncode=0)
    svcs = system_change_tracker.get_linux_services()
    assert svcs.get("ssh") == "running"
    assert svcs.get("cron") == "running"


def test_diff_snapshots() -> None:
    """Test differential snapshot calculation logic."""
    before = {
        "files": {
            "file1.txt": {"size": 10, "sha256": "h1"},
            "file2.txt": {"size": 20, "sha256": "h2"},
        },
        "env": {"PATH": "/bin", "DELETED_VAR": "val"},
        "python_packages": {"pytest": "8.2.0"},
        "system_packages": {"curl": "7.8.0"},
        "services": {"ssh": "running"},
    }

    after = {
        "files": {
            "file1.txt": {"size": 12, "sha256": "h1_mod"},  # Modified
            "file3.txt": {"size": 30, "sha256": "h3"},  # Added
        },
        "env": {"PATH": "/bin:/sbin", "ADDED_VAR": "newval"},  # Modified & Added
        "python_packages": {"pytest": "8.2.2", "black": "24.4.2"},  # Modified & Added
        "system_packages": {},  # Deleted
        "services": {"ssh": "stopped"},  # Modified
    }

    diff = system_change_tracker.diff_snapshots(before, after)

    # Verify Files
    assert "file3.txt" in diff["files"]["added"]
    assert "file2.txt" in diff["files"]["deleted"]
    assert len(diff["files"]["modified"]) == 1
    assert diff["files"]["modified"][0]["path"] == "file1.txt"

    # Verify Env
    assert "ADDED_VAR" in diff["env"]["added"]
    assert "DELETED_VAR" in diff["env"]["deleted"]
    assert diff["env"]["modified"]["PATH"]["after"] == "/bin:/sbin"

    # Verify Python packages
    assert "black" in diff["python_packages"]["added"]
    assert diff["python_packages"]["modified"]["pytest"]["after"] == "8.2.2"

    # Verify System packages
    assert "curl" in diff["system_packages"]["deleted"]

    # Verify Services
    assert diff["services"]["modified"]["ssh"]["after"] == "stopped"


def test_print_diff_dashboard(capsys: pytest.CaptureFixture[str]) -> None:
    """Test stdout console report formatting of diff changes."""
    diff = {
        "files": {
            "added": ["f_add.txt"],
            "deleted": ["f_del.txt"],
            "modified": [
                {
                    "path": "f_mod.txt",
                    "before": {"size": 10, "sha256": "a"},
                    "after": {"size": 15, "sha256": "b"},
                }
            ],
        },
        "env": {"added": {"NEW_V": "x"}, "deleted": ["OLD_V"], "modified": {}},
        "python_packages": {
            "added": {"mypy": "1.0"},
            "deleted": [],
            "modified": {},
        },
        "system_packages": {"added": {}, "deleted": {}, "modified": {}},
        "services": {"added": {}, "deleted": {}, "modified": {}},
    }

    system_change_tracker.print_diff_dashboard(diff)
    captured = capsys.readouterr()
    assert "SYSTEM CHANGELOG REPORT" in captured.out
    assert "f_add.txt" in captured.out
    assert "f_del.txt" in captured.out
    assert "NEW_V" in captured.out
    assert "mypy" in captured.out


@patch("sys.exit")
def test_main_cli_snapshot(mock_exit: MagicMock, tmp_path: Path) -> None:
    """Test CLI main snapshot command execution."""
    out_json = tmp_path / "snap.json"
    args = [
        "system_change_tracker.py",
        "snapshot",
        "-o",
        str(out_json),
        "-d",
        str(tmp_path),
    ]

    with patch("sys.argv", args):
        system_change_tracker.main()
        assert out_json.exists()
        saved = json.loads(out_json.read_text(encoding="utf-8"))
        assert "timestamp" in saved
        assert "files" in saved
        assert "env" in saved


def test_main_cli_diff(tmp_path: Path) -> None:
    """Test CLI main diff command execution."""
    snap1 = tmp_path / "snap1.json"
    snap2 = tmp_path / "snap2.json"
    out_diff = tmp_path / "diff.json"

    data1 = {
        "timestamp": "t1",
        "files": {},
        "env": {},
        "python_packages": {},
        "system_packages": {},
        "services": {},
    }
    data2 = {
        "timestamp": "t2",
        "files": {},
        "env": {},
        "python_packages": {},
        "system_packages": {},
        "services": {},
    }

    snap1.write_text(json.dumps(data1))
    snap2.write_text(json.dumps(data2))

    args = [
        "system_change_tracker.py",
        "diff",
        str(snap1),
        str(snap2),
        "-o",
        str(out_diff),
    ]
    with patch("sys.argv", args):
        system_change_tracker.main()
        assert out_diff.exists()
        diff_res = json.loads(out_diff.read_text(encoding="utf-8"))
        assert "files" in diff_res
        assert "env" in diff_res


def test_platform_fallback() -> None:
    """Test package and service lookup falls back gracefully on other OS types."""
    # 1. Linux mocked queries
    with patch("sys.platform", "linux"), patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(stdout="pkg 1.0\n", returncode=0)
        assert "pkg" in system_change_tracker.get_system_packages()

        mock_run.return_value = MagicMock(
            stdout="ssh.service loaded active running Description\n", returncode=0
        )
        assert "ssh" in system_change_tracker.get_system_services()

    # 2. Unsupported macOS/darwin fallback
    with patch("sys.platform", "darwin"):
        assert system_change_tracker.get_system_packages() == {}
        assert system_change_tracker.get_system_services() == {}


def test_main_cli_errors_and_fallbacks(tmp_path: Path) -> None:
    """Test CLI error reporting pathways."""
    # 1. Nonexistent directory input in snapshot (does not throw)
    out_json = tmp_path / "snap_error.json"
    args = [
        "system_change_tracker.py",
        "snapshot",
        "-o",
        str(out_json),
        "-d",
        "nonexistent_dir",
    ]
    with patch("sys.argv", args):
        system_change_tracker.main()
        assert out_json.exists()

    # 2. Snapshot file save OSError (raises SystemExit 1)
    args2 = ["system_change_tracker.py", "snapshot", "-o", "/read_only_path/snap.json"]
    with patch("sys.argv", args2):
        with pytest.raises(SystemExit) as exc:
            system_change_tracker.main()
        assert exc.value.code == 1

    # 3. Diff command nonexistent files (raises SystemExit 1)
    args3 = [
        "system_change_tracker.py",
        "diff",
        "nonexistent1.json",
        "nonexistent2.json",
    ]
    with patch("sys.argv", args3):
        with pytest.raises(SystemExit) as exc:
            system_change_tracker.main()
        assert exc.value.code == 1
