"""Unit tests for the failure-pack script."""

import os
import sys
from unittest.mock import MagicMock, patch

# Insert parent dir to PATH to support folder-based import
sys.path.insert(0, "tools/failure-pack")

from failure_pack import (  # noqa: E402
    find_related_logs_and_configs,
    get_system_diagnostics,
    main,
)


def test_get_system_diagnostics_success():
    # platform.architecture() shells out to the OS 'file' utility on POSIX,
    # which would consume the mocked subprocess.run; pin it cross-platform.
    with patch("subprocess.run") as mock_run, patch(
        "platform.architecture", return_value=("64bit", "ELF")
    ):
        mock_res = MagicMock()
        mock_res.returncode = 0
        mock_res.stdout = '[{"name": "pip", "version": "21.0.1"}]'
        mock_run.return_value = mock_res

        diag = get_system_diagnostics()
        assert isinstance(diag, dict)
        assert "timestamp" in diag
        assert "platform" in diag
        assert "system" in diag
        assert "environment_variable_keys" in diag
        assert diag["installed_packages"] == [{"name": "pip", "version": "21.0.1"}]


def test_get_system_diagnostics_failure():
    with patch("subprocess.run", side_effect=OSError("error")):
        diag = get_system_diagnostics()
        assert isinstance(diag, dict)
        assert diag["installed_packages"] == []


def test_find_related_logs_and_configs():
    mock_walk_data = [
        (
            "root",
            ["venv", "good_dir"],
            ["app.log", "pyproject.toml", ".env", "large.log"],
        ),
        ("root/good_dir", [], ["requirements.txt", "other.py"]),
    ]

    def mock_getsize(path):
        if "large.log" in path:
            return 300 * 1024
        return 10 * 1024

    with patch("os.walk", return_value=mock_walk_data), patch(
        "os.path.getsize", side_effect=mock_getsize
    ):
        discovered = find_related_logs_and_configs("root")

        expected = [
            os.path.join("root", "app.log"),
            os.path.join("root", "pyproject.toml"),
            os.path.join("root/good_dir", "requirements.txt"),
        ]
        assert sorted(discovered) == sorted(expected)


def test_main_no_command():
    with patch("sys.argv", ["failure_pack.py"]):
        try:
            main()
        except SystemExit as exc:
            assert exc.code == 1


def test_main_command_success_no_force():
    with patch("sys.argv", ["failure_pack.py", "--", "echo", "hello"]), patch(
        "subprocess.run"
    ) as mock_run:
        mock_res = MagicMock()
        mock_res.returncode = 0
        mock_res.stdout = "hello\n"
        mock_run.return_value = mock_res

        try:
            main()
        except SystemExit as exc:
            assert exc.code == 0
        mock_run.assert_called_once()
        assert mock_run.call_args[1]["shell"] is True


@patch("zipfile.ZipFile")
@patch("os.getcwd", return_value="mock_cwd")
@patch("failure_pack.find_related_logs_and_configs", return_value=["mock_cwd/app.log"])
@patch("failure_pack.get_system_diagnostics", return_value={"mock": "diag"})
def test_main_command_failed_or_forced(
    mock_get_diag, mock_find_files, mock_getcwd, mock_zipfile
):
    with patch("sys.argv", ["failure_pack.py", "--", "false"]), patch(
        "subprocess.run"
    ) as mock_run:

        mock_res = MagicMock()
        mock_res.returncode = 1
        mock_res.stdout = "some stdout"
        mock_res.stderr = "some stderr"
        mock_run.return_value = mock_res

        main()

        mock_zipfile.assert_called_once()
        zip_inst = mock_zipfile.return_value.__enter__.return_value

        writestr_calls = zip_inst.writestr.call_args_list
        assert any(c[0][0] == "diagnostics_report.json" for c in writestr_calls)
        assert any(c[0][0] == "stdout.log" for c in writestr_calls)
        assert any(c[0][0] == "stderr.log" for c in writestr_calls)

        zip_inst.write.assert_called_once_with(
            "mock_cwd/app.log", os.path.join("workspace", "app.log")
        )
