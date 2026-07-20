import json
import os
import sys
from unittest.mock import MagicMock, patch

import pytest

# Add parent directory to sys.path to import context_switch
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
import context_switch  # noqa: E402


@pytest.fixture
def run_in_tmp_dir(tmp_path):
    old_cwd = os.getcwd()
    os.chdir(tmp_path)
    yield tmp_path
    os.chdir(old_cwd)


def test_get_current_branch_success():
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(stdout="my-feature-branch\n")
        branch = context_switch.get_current_branch("dummy_dir")
        assert branch == "my-feature-branch"
        mock_run.assert_called_once_with(
            ["git", "branch", "--show-current"],
            cwd="dummy_dir",
            stdout=-1,
            stderr=-1,
            text=True,
            check=False,
        )


def test_get_current_branch_exception():
    with patch("subprocess.run", side_effect=Exception):
        assert context_switch.get_current_branch("dummy_dir") == "Unknown"


def test_get_listening_ports_no_psutil():
    with patch("context_switch.HAS_PSUTIL", False):
        assert context_switch.get_listening_ports() == []


def test_get_listening_ports_with_psutil():
    class DummyConn:
        def __init__(self, status, port):
            self.status = status
            self.laddr = MagicMock(port=port)

    conns = [
        DummyConn("LISTEN", 8080),
        DummyConn("LISTEN", 3000),
        DummyConn("LISTEN", 1234),
        DummyConn("CLOSE_WAIT", 8080),
    ]

    mock_psutil = MagicMock()
    mock_psutil.net_connections.return_value = conns

    orig_has_psutil = context_switch.HAS_PSUTIL
    orig_psutil = getattr(context_switch, "psutil", None)

    context_switch.HAS_PSUTIL = True
    context_switch.psutil = mock_psutil

    try:
        ports = context_switch.get_listening_ports()
        assert set(ports) == {8080, 3000}
    finally:
        context_switch.HAS_PSUTIL = orig_has_psutil
        if orig_psutil is not None:
            context_switch.psutil = orig_psutil
        else:
            delattr(context_switch, "psutil")


def test_run_save_non_git(run_in_tmp_dir):
    storage_dir = run_in_tmp_dir / "storage"
    storage_dir.mkdir()

    with patch("context_switch.get_listening_ports", return_value=[8080]):
        context_switch.run_save("test-ctx", str(storage_dir), "My notes here")

    json_path = storage_dir / "test-ctx.json"
    assert json_path.exists()
    with open(json_path, "r", encoding="utf-8") as f:
        meta = json.load(f)

    assert meta["name"] == "test-ctx"
    assert meta["branch"] == "N/A"
    assert meta["has_patch"] is False
    assert meta["ports"] == [8080]
    assert meta["notes"] == "My notes here"
    assert not (storage_dir / "test-ctx.patch").exists()


def test_run_save_git_dirty(run_in_tmp_dir):
    storage_dir = run_in_tmp_dir / "storage"
    storage_dir.mkdir()

    (run_in_tmp_dir / ".git").mkdir()

    with patch("context_switch.get_current_branch", return_value="main"), patch(
        "context_switch.get_listening_ports", return_value=[]
    ), patch("subprocess.run") as mock_run:

        mock_status = MagicMock(stdout=" M file.py\n")
        mock_diff = MagicMock()
        mock_run.side_effect = [mock_status, mock_diff]

        context_switch.run_save("test-ctx-git", str(storage_dir), "")

    json_path = storage_dir / "test-ctx-git.json"
    assert json_path.exists()
    with open(json_path, "r", encoding="utf-8") as f:
        meta = json.load(f)

    assert meta["branch"] == "main"
    assert meta["has_patch"] is True
    assert (storage_dir / "test-ctx-git.patch").exists()


def test_run_restore(run_in_tmp_dir):
    storage_dir = run_in_tmp_dir / "storage"
    storage_dir.mkdir()

    meta = {
        "name": "restore-ctx",
        "timestamp": "2026-07-19T22:50:14",
        "directory": os.getcwd(),
        "branch": "feature-abc",
        "has_patch": True,
        "ports": [8080, 9000],
        "notes": "TODO: fix bug",
    }
    with open(storage_dir / "restore-ctx.json", "w") as fh:
        json.dump(meta, fh)

    with open(storage_dir / "restore-ctx.patch", "w") as fh:
        fh.write("dummy patch content")

    (run_in_tmp_dir / ".git").mkdir()

    with patch("context_switch.get_current_branch", return_value="main"), patch(
        "context_switch.get_listening_ports", return_value=[8080]
    ), patch("subprocess.run") as mock_run:

        from io import StringIO

        new_stdout = StringIO()
        with patch("sys.stdout", new_stdout):
            context_switch.run_restore("restore-ctx", str(storage_dir))

        output = new_stdout.getvalue()
        mock_run.assert_any_call(
            ["git", "checkout", "feature-abc"], cwd=os.getcwd(), check=False
        )
        mock_run.assert_any_call(
            ["git", "apply", os.path.join(str(storage_dir), "restore-ctx.patch")],
            cwd=os.getcwd(),
            check=False,
        )

        assert (
            "Dev servers previously listening on ports [9000] are not active" in output
        )
        assert "TODO: fix bug" in output


def test_run_list(run_in_tmp_dir):
    storage_dir = run_in_tmp_dir / "storage"
    storage_dir.mkdir()

    meta1 = {
        "name": "profile1",
        "timestamp": "2026-07-19T10:00:00",
        "directory": "/home/dev/proj1",
        "branch": "master",
    }
    meta2 = {
        "name": "profile2",
        "timestamp": "2026-07-19T11:00:00",
        "directory": "/home/dev/proj2-long-path-name-to-test-truncation",
        "branch": "dev",
    }
    with open(storage_dir / "profile1.json", "w") as fh:
        json.dump(meta1, fh)
    with open(storage_dir / "profile2.json", "w") as fh:
        json.dump(meta2, fh)

    from io import StringIO

    new_stdout = StringIO()
    with patch("sys.stdout", new_stdout):
        context_switch.run_list(str(storage_dir))

    output = new_stdout.getvalue()
    assert "profile1" in output
    assert "profile2" in output
    assert "master" in output
    assert "dev" in output
    assert "..." in output


def test_main_save(run_in_tmp_dir):
    with patch(
        "sys.argv", ["context_switch.py", "save", "my-context", "-n", "some task info"]
    ), patch("context_switch.run_save") as mock_save:
        context_switch.main()
        mock_save.assert_called_once()
        args, kwargs = mock_save.call_args
        assert args[0] == "my-context"
        assert args[2] == "some task info"


def test_main_restore(run_in_tmp_dir):
    with patch("sys.argv", ["context_switch.py", "restore", "my-context"]), patch(
        "context_switch.run_restore"
    ) as mock_restore:
        context_switch.main()
        mock_restore.assert_called_once()
        args, kwargs = mock_restore.call_args
        assert args[0] == "my-context"


def test_main_list(run_in_tmp_dir):
    with patch("sys.argv", ["context_switch.py", "list"]), patch(
        "context_switch.run_list"
    ) as mock_list:
        context_switch.main()
        mock_list.assert_called_once()
