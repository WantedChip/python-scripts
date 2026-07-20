import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, mock_open, patch

import pytest

# Add the script's directory to the python path to load the module correctly
script_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(script_dir))

import scheduled_task_auditor  # noqa: E402


@patch("scheduled_task_auditor.sys.platform", "linux")
def test_get_windows_tasks_non_windows():
    assert scheduled_task_auditor.get_windows_tasks() == []


@patch("scheduled_task_auditor.sys.platform", "win32")
@patch("scheduled_task_auditor.subprocess.run")
def test_get_windows_tasks_success(mock_run):
    mock_stdout = (
        '"TaskName","Task To Run","Status","Trigger Type"\n'
        '"\\MyTask","C:\\path\\to\\app.exe","Ready","Daily"\n'
        '"\\AnotherTask","""C:\\Program Files\\app2.exe"" --arg","Running","Weekly"\n'
    )
    mock_run.return_value = MagicMock(returncode=0, stdout=mock_stdout)
    tasks = scheduled_task_auditor.get_windows_tasks()
    assert len(tasks) == 2
    assert tasks[0] == {
        "name": "\\MyTask",
        "command": "C:\\path\\to\\app.exe",
        "source": "Task Scheduler",
        "trigger": "Daily",
        "status": "Ready",
    }
    assert tasks[1] == {
        "name": "\\AnotherTask",
        "command": '"C:\\Program Files\\app2.exe" --arg',
        "source": "Task Scheduler",
        "trigger": "Weekly",
        "status": "Running",
    }


@patch("scheduled_task_auditor.sys.platform", "win32")
@patch("scheduled_task_auditor.subprocess.run")
def test_get_windows_tasks_failure(mock_run):
    mock_run.return_value = MagicMock(returncode=1)
    assert scheduled_task_auditor.get_windows_tasks() == []


@patch("scheduled_task_auditor.sys.platform", "win32")
@patch("scheduled_task_auditor.subprocess.run")
def test_get_windows_tasks_exception(mock_run):
    mock_run.side_effect = Exception("error")
    assert scheduled_task_auditor.get_windows_tasks() == []


@patch("scheduled_task_auditor.sys.platform", "linux")
def test_get_windows_startup_entries_non_windows():
    assert scheduled_task_auditor.get_windows_startup_entries() == []


@patch("scheduled_task_auditor.sys.platform", "win32")
@patch.dict(
    "scheduled_task_auditor.os.environ",
    {"USERPROFILE": "C:\\Users\\test", "ProgramData": "C:\\ProgramData"},
)
@patch("scheduled_task_auditor.os.path.exists")
@patch("scheduled_task_auditor.os.listdir")
def test_get_windows_startup_entries_success(mock_listdir, mock_exists):
    mock_exists.return_value = True
    mock_listdir.side_effect = [["user_shortcut.lnk"], ["system_shortcut.lnk"]]

    entries = scheduled_task_auditor.get_windows_startup_entries()
    assert len(entries) == 2
    assert entries[0]["name"] == "user_shortcut.lnk"
    assert entries[0]["source"] == "Startup Folder"
    assert entries[1]["name"] == "system_shortcut.lnk"


@patch("scheduled_task_auditor.sys.platform", "win32")
@patch.dict(
    "scheduled_task_auditor.os.environ",
    {"USERPROFILE": "C:\\Users\\test", "ProgramData": "C:\\ProgramData"},
)
@patch("scheduled_task_auditor.os.path.exists")
@patch("scheduled_task_auditor.os.listdir")
def test_get_windows_startup_entries_os_error(mock_listdir, mock_exists):
    mock_exists.return_value = True
    mock_listdir.side_effect = OSError("Access denied")
    assert scheduled_task_auditor.get_windows_startup_entries() == []


@patch("scheduled_task_auditor.sys.platform", "win32")
def test_get_unix_cron_entries_win32():
    assert scheduled_task_auditor.get_unix_cron_entries() == []


@patch("scheduled_task_auditor.sys.platform", "linux")
@patch("scheduled_task_auditor.os.path.exists")
@patch("scheduled_task_auditor.os.path.isfile")
@patch("scheduled_task_auditor.os.listdir")
@patch("scheduled_task_auditor.subprocess.run")
def test_get_unix_cron_entries_success(
    mock_run, mock_listdir, mock_isfile, mock_exists
):
    def exists_side_effect(path):
        normalized = os.path.normpath(path)
        expected_paths = [
            os.path.normpath("/etc/cron.d"),
            os.path.normpath("/etc/cron.daily"),
            os.path.normpath("/etc/crontab"),
            os.path.normpath("/etc/cron.d/an_entry"),
            os.path.normpath("/etc/cron.daily/daily_entry"),
        ]
        return normalized in expected_paths

    def isfile_side_effect(path):
        return True

    mock_exists.side_effect = exists_side_effect
    mock_isfile.side_effect = isfile_side_effect

    def listdir_side_effect(path):
        normalized = os.path.normpath(path)
        if normalized == os.path.normpath("/etc/cron.d"):
            return ["an_entry"]
        if normalized == os.path.normpath("/etc/cron.daily"):
            return ["daily_entry"]
        return []

    mock_listdir.side_effect = listdir_side_effect

    cron_content = "1 2 * * * root /usr/bin/some_cmd"
    m_open = mock_open(read_data=cron_content)

    mock_run.return_value = MagicMock(
        returncode=0, stdout="3 4 * * * /usr/bin/user_cmd\n# comment"
    )

    with patch("builtins.open", m_open):
        entries = scheduled_task_auditor.get_unix_cron_entries()

    assert len(entries) == 4
    assert entries[0]["name"] == "crontab:line_1"
    assert entries[0]["command"] == "1 2 * * * root /usr/bin/some_cmd"
    assert entries[3]["name"] == "User Crontab:line_1"
    assert entries[3]["command"] == "3 4 * * * /usr/bin/user_cmd"


@patch("scheduled_task_auditor.sys.platform", "linux")
@patch("scheduled_task_auditor.os.path.exists")
@patch("scheduled_task_auditor.subprocess.run")
def test_get_unix_cron_entries_failure(mock_run, mock_exists):
    mock_exists.return_value = False
    mock_run.return_value = MagicMock(returncode=1)
    assert scheduled_task_auditor.get_unix_cron_entries() == []


@patch("scheduled_task_auditor.sys.platform", "win32")
def test_get_unix_systemd_timers_win32():
    assert scheduled_task_auditor.get_unix_systemd_timers() == []


@patch("scheduled_task_auditor.sys.platform", "linux")
@patch("scheduled_task_auditor.os.path.exists")
@patch("scheduled_task_auditor.os.listdir")
def test_get_unix_systemd_timers_success(mock_listdir, mock_exists):
    def exists_side_effect(path):
        normalized = os.path.normpath(path)
        if normalized == os.path.normpath("/etc/systemd/system/"):
            return True
        if normalized == os.path.normpath("/etc/systemd/system/test.service"):
            return True
        return False

    mock_exists.side_effect = exists_side_effect

    mock_listdir.side_effect = [["test.timer", "other_file.conf"], []]

    service_content = "[Service]\nExecStart=/usr/bin/my_service_cmd --arg"
    m_open = mock_open(read_data=service_content)

    with patch("builtins.open", m_open):
        entries = scheduled_task_auditor.get_unix_systemd_timers()

    assert len(entries) == 1
    assert entries[0] == {
        "name": "test.timer",
        "command": "/usr/bin/my_service_cmd --arg",
        "source": "Systemd Timer",
        "trigger": "Systemd Schedule",
        "status": "Active",
    }


@patch("scheduled_task_auditor.sys.platform", "linux")
@patch("scheduled_task_auditor.os.path.exists")
@patch("scheduled_task_auditor.os.listdir")
def test_get_unix_systemd_timers_no_service(mock_listdir, mock_exists):
    def exists_side_effect(path):
        normalized = os.path.normpath(path)
        if normalized == os.path.normpath("/etc/systemd/system/"):
            return True
        return False

    mock_exists.side_effect = exists_side_effect
    mock_listdir.side_effect = [["test.timer"], []]

    entries = scheduled_task_auditor.get_unix_systemd_timers()
    assert len(entries) == 1
    assert entries[0]["command"] == "Unknown (matching service missing)"


def test_parse_executable():
    assert scheduled_task_auditor.parse_executable("") == ""
    assert scheduled_task_auditor.parse_executable("   ") == ""
    assert (
        scheduled_task_auditor.parse_executable('"C:\\Program Files\\App.exe" -arg')
        == "C:\\Program Files\\App.exe"
    )
    assert (
        scheduled_task_auditor.parse_executable("'relative/path/to/script.sh' --run")
        == "relative/path/to/script.sh"
    )
    assert scheduled_task_auditor.parse_executable("python3 main.py") == "python3"
    assert scheduled_task_auditor.parse_executable("cmd.exe") == "cmd.exe"


@patch("scheduled_task_auditor.os.path.exists")
@patch("scheduled_task_auditor.shutil.which")
def test_audit_command(mock_which, mock_exists):
    # Empty command
    lvl, reason = scheduled_task_auditor.audit_command("")
    assert lvl == "Unknown"

    # Path indicator exists
    mock_exists.return_value = True
    lvl, reason = scheduled_task_auditor.audit_command("/usr/bin/python3")
    assert lvl == "OK"
    assert "verified" in reason

    # Path indicator does not exist
    mock_exists.return_value = False
    lvl, reason = scheduled_task_auditor.audit_command("/usr/bin/missing_tool")
    assert lvl == "Critical"
    assert "does not exist" in reason

    # No path indicator, found in PATH
    mock_which.return_value = "/usr/bin/git"
    lvl, reason = scheduled_task_auditor.audit_command("git status")
    assert lvl == "OK"
    assert "found on PATH" in reason

    # No path indicator, not found in PATH
    mock_which.return_value = None
    lvl, reason = scheduled_task_auditor.audit_command("not_real_tool")
    assert lvl == "Warning"
    assert "not found on active PATH" in reason


@patch("scheduled_task_auditor.sys.platform", "win32")
@patch("scheduled_task_auditor.get_windows_tasks")
@patch("scheduled_task_auditor.get_windows_startup_entries")
def test_main_no_tasks(mock_startup, mock_tasks):
    mock_tasks.return_value = []
    mock_startup.return_value = []

    with patch("sys.argv", ["scheduled_task_auditor.py"]):
        with pytest.raises(SystemExit) as exc_info:
            scheduled_task_auditor.main()
    assert exc_info.value.code == 0


@patch("scheduled_task_auditor.sys.platform", "linux")
@patch("scheduled_task_auditor.get_unix_cron_entries")
@patch("scheduled_task_auditor.get_unix_systemd_timers")
@patch("scheduled_task_auditor.audit_command")
def test_main_all_ok(mock_audit, mock_timers, mock_cron):
    mock_cron.return_value = [
        {
            "name": "cron1",
            "command": "/bin/true",
            "source": "cron",
            "trigger": "t",
            "status": "Active",
        }
    ]
    mock_timers.return_value = []
    mock_audit.return_value = ("OK", "Path verified")

    with patch("sys.argv", ["scheduled_task_auditor.py"]):
        with pytest.raises(SystemExit) as exc_info:
            scheduled_task_auditor.main()
    assert exc_info.value.code == 0


@patch("scheduled_task_auditor.sys.platform", "linux")
@patch("scheduled_task_auditor.get_unix_cron_entries")
@patch("scheduled_task_auditor.get_unix_systemd_timers")
@patch("scheduled_task_auditor.audit_command")
def test_main_with_issues(mock_audit, mock_timers, mock_cron):
    mock_cron.return_value = [
        {
            "name": "cron1",
            "command": "/bin/true",
            "source": "cron",
            "trigger": "t",
            "status": "Active",
        },
        {
            "name": "cron2",
            "command": "/bin/false",
            "source": "cron",
            "trigger": "t",
            "status": "Active",
        },
    ]
    mock_timers.return_value = []

    def audit_side_effect(cmd):
        if cmd == "/bin/true":
            return ("Warning", "warning reason")
        return ("Critical", "critical reason")

    mock_audit.side_effect = audit_side_effect

    # Does not call sys.exit, runs to completion
    with patch("sys.argv", ["scheduled_task_auditor.py"]):
        scheduled_task_auditor.main()
