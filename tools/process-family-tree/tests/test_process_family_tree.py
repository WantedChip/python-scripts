import os
import sys
from unittest.mock import MagicMock, patch

import pytest

# Ensure psutil mock exists in sys.modules and has the required exceptions
if "psutil" not in sys.modules:
    mock_psutil = MagicMock()
    sys.modules["psutil"] = mock_psutil
else:
    mock_psutil = sys.modules["psutil"]


class MockNoSuchProcess(Exception):
    pass


class MockAccessDenied(Exception):
    pass


mock_psutil.NoSuchProcess = MockNoSuchProcess
mock_psutil.AccessDenied = MockAccessDenied

# Add target directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
import process_family_tree  # noqa: E402


def test_format_process_info_success():
    proc = MagicMock()
    proc.pid = 123
    proc.name.return_value = "python"
    proc.username.return_value = "alice"
    proc.cmdline.return_value = ["python", "main.py", "--arg"]
    proc.cwd.return_value = "/home/alice"

    mock_conn = MagicMock()
    mock_conn.status = "LISTEN"
    mock_conn.laddr.port = 8080
    proc.connections.return_value = [mock_conn]

    info = process_family_tree.format_process_info(proc)
    assert (
        "python (PID: 123, Owner: alice) [CWD: /home/alice] [Listening :8080]" in info
    )
    assert "Cmd: python main.py --arg" in info


def test_format_process_info_truncated_cmd():
    proc = MagicMock()
    proc.pid = 123
    proc.name.return_value = "python"
    proc.username.return_value = "alice"
    proc.cmdline.return_value = ["python", "main.py"] + [
        "--very-long-argument-flag-here"
    ] * 5
    proc.cwd.return_value = "/home/alice"
    proc.connections.return_value = []

    info = process_family_tree.format_process_info(proc)
    assert len(info.split("\n")[1].strip()) <= len("  └─ Cmd: ") + 60


def test_format_process_info_access_denied_fields():
    proc = MagicMock()
    proc.pid = 123
    proc.name.return_value = "python"
    proc.username.side_effect = MockAccessDenied()
    proc.cmdline.side_effect = MockAccessDenied()
    proc.cwd.side_effect = MockAccessDenied()
    proc.connections.side_effect = MockAccessDenied()

    info = process_family_tree.format_process_info(proc)
    assert "python (PID: 123, Owner: Unknown) [CWD: N/A]" in info
    assert "Cmd: N/A" in info


def test_format_process_info_process_dead():
    proc = MagicMock()
    proc.pid = 123
    proc.name.side_effect = MockNoSuchProcess()

    info = process_family_tree.format_process_info(proc)
    assert "Process (PID: 123) [Access Denied / Ended]" in info


def test_print_tree(capsys):
    target = MagicMock()
    target.pid = 200
    target.name.return_value = "target"
    target.username.return_value = "user"
    target.cmdline.return_value = ["target-bin"]
    target.cwd.return_value = "/cwd"
    target.connections.return_value = []

    ancestor = MagicMock()
    ancestor.pid = 100
    ancestor.name.return_value = "parent"
    ancestor.username.return_value = "user"
    ancestor.cmdline.return_value = ["parent-bin"]
    ancestor.cwd.return_value = "/cwd"
    ancestor.connections.return_value = []

    child = MagicMock()
    child.pid = 300
    child.name.return_value = "child"
    child.username.return_value = "user"
    child.cmdline.return_value = ["child-bin"]
    child.cwd.return_value = "/cwd"
    child.connections.return_value = []

    process_family_tree.print_tree([ancestor], target, [child])
    captured = capsys.readouterr()
    assert "Ancestry Lineage" in captured.out
    assert "parent" in captured.out
    assert "[TARGET] target" in captured.out
    assert "Child Processes:" in captured.out
    assert "child" in captured.out


def test_print_tree_no_children(capsys):
    target = MagicMock()
    target.pid = 200
    target.name.return_value = "target"
    target.username.return_value = "user"
    target.cmdline.return_value = []
    target.cwd.return_value = "/cwd"
    target.connections.return_value = []

    process_family_tree.print_tree([], target, [])
    captured = capsys.readouterr()
    assert "Child Processes: None active" in captured.out


def test_find_process_by_name():
    proc1 = MagicMock()
    proc1.info = {"name": "Python.exe"}
    proc2 = MagicMock()
    proc2.info = {"name": "Node.js"}
    proc3 = MagicMock()
    proc3.info = {"name": "Pytest-run"}

    with patch(
        "process_family_tree.psutil.process_iter", return_value=[proc1, proc2, proc3]
    ):
        matches = process_family_tree.find_process_by_name("py")
        assert len(matches) == 2
        assert proc1 in matches
        assert proc3 in matches


def test_find_process_by_name_exceptions():
    proc1 = MagicMock()
    type(proc1).info = property(lambda self: (_ for _ in ()).throw(MockNoSuchProcess()))

    with patch("process_family_tree.psutil.process_iter", return_value=[proc1]):
        matches = process_family_tree.find_process_by_name("py")
        assert matches == []


def test_main_no_psutil(capsys):
    with patch("process_family_tree.HAS_PSUTIL", False), patch(
        "sys.argv", ["process_family_tree.py"]
    ), pytest.raises(SystemExit) as exc_info:
        process_family_tree.main()

    assert exc_info.value.code == 1
    captured = capsys.readouterr()
    assert "Required library 'psutil' is not installed" in captured.err


def test_main_default_target_success():
    mock_curr = MagicMock()
    mock_curr.pid = 123
    mock_parent = MagicMock()
    mock_parent.pid = 10
    mock_curr.parent.return_value = mock_parent
    mock_parent.parent.return_value = None
    mock_curr.children.return_value = []

    with patch("process_family_tree.HAS_PSUTIL", True), patch(
        "sys.argv", ["process_family_tree.py"]
    ), patch("os.getpid", return_value=123), patch(
        "process_family_tree.psutil.Process", return_value=mock_curr
    ), patch(
        "process_family_tree.print_tree"
    ) as mock_print:
        process_family_tree.main()

        mock_curr.parent.assert_called()
        mock_print.assert_called_once()
        args, kwargs = mock_print.call_args
        assert args[0] == [mock_parent]
        assert args[1] == mock_curr
        assert args[2] == []


def test_main_target_pid_success():
    mock_target = MagicMock()
    mock_target.pid = 456
    mock_target.parent.return_value = None
    mock_target.children.return_value = []

    with patch("process_family_tree.HAS_PSUTIL", True), patch(
        "sys.argv", ["process_family_tree.py", "456"]
    ), patch("process_family_tree.psutil.Process", return_value=mock_target), patch(
        "process_family_tree.print_tree"
    ) as mock_print:
        process_family_tree.main()
        mock_print.assert_called_once_with([], mock_target, [])


def test_main_target_pid_not_found(capsys):
    with patch("process_family_tree.HAS_PSUTIL", True), patch(
        "sys.argv", ["process_family_tree.py", "9999"]
    ), patch(
        "process_family_tree.psutil.Process", side_effect=MockNoSuchProcess()
    ), pytest.raises(
        SystemExit
    ) as exc_info:
        process_family_tree.main()

    assert exc_info.value.code == 1
    captured = capsys.readouterr()
    assert "No active process found with PID: 9999" in captured.err


def test_main_target_name_no_matches(capsys):
    with patch("process_family_tree.HAS_PSUTIL", True), patch(
        "sys.argv", ["process_family_tree.py", "nonexistent_proc"]
    ), patch(
        "process_family_tree.find_process_by_name", return_value=[]
    ), pytest.raises(
        SystemExit
    ) as exc_info:
        process_family_tree.main()

    assert exc_info.value.code == 1
    captured = capsys.readouterr()
    assert "No processes matched name query: 'nonexistent_proc'" in captured.err


def test_main_target_name_single_match():
    mock_matched = MagicMock()
    mock_matched.pid = 111
    mock_matched.parent.return_value = None
    mock_matched.children.return_value = []

    with patch("process_family_tree.HAS_PSUTIL", True), patch(
        "sys.argv", ["process_family_tree.py", "myproc"]
    ), patch(
        "process_family_tree.find_process_by_name", return_value=[mock_matched]
    ), patch(
        "process_family_tree.print_tree"
    ) as mock_print:
        process_family_tree.main()
        mock_print.assert_called_once_with([], mock_matched, [])


def test_main_target_name_multiple_matches(capsys):
    proc1 = MagicMock()
    proc1.pid = 111
    proc1.name.return_value = "myproc"
    proc2 = MagicMock()
    proc2.pid = 222
    proc2.name.return_value = "myproc-helper"

    with patch("process_family_tree.HAS_PSUTIL", True), patch(
        "sys.argv", ["process_family_tree.py", "myproc"]
    ), patch(
        "process_family_tree.find_process_by_name", return_value=[proc1, proc2]
    ), pytest.raises(
        SystemExit
    ) as exc_info:
        process_family_tree.main()

    assert exc_info.value.code == 1
    captured = capsys.readouterr()
    assert "Multiple processes matched 'myproc':" in captured.out
    assert "Please specify a unique PID" in captured.err
