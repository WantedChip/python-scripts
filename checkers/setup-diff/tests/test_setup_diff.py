import gettext
import json
import os
import sys
from unittest.mock import MagicMock, mock_open, patch

import pytest

# Ensure target directory is in path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
import setup_diff  # noqa: E402


@pytest.fixture(autouse=True)
def _stub_gettext_catalog():
    """Stub gettext catalog loading so argparse never opens files via mocked open()."""
    with patch(
        "gettext.translation", lambda *args, **kwargs: gettext.NullTranslations()
    ):
        yield


def test_check_binary():
    with patch("shutil.which") as mock_which:
        mock_which.side_effect = lambda x: f"/path/to/{x}" if x == "git" else None
        assert setup_diff.check_binary("git") == "/path/to/git"
        assert setup_diff.check_binary("nonexistent") is None


def test_get_listening_ports_no_psutil():
    with patch("setup_diff.HAS_PSUTIL", False):
        assert setup_diff.get_listening_ports() == []


def test_get_listening_ports_with_psutil():
    mock_psutil = MagicMock()
    mock_conn1 = MagicMock()
    mock_conn1.status = "LISTEN"
    mock_conn1.laddr.port = 8080

    mock_conn2 = MagicMock()
    mock_conn2.status = "LISTEN"
    mock_conn2.laddr.port = 9000

    mock_conn3 = MagicMock()
    mock_conn3.status = "ESTABLISHED"
    mock_conn3.laddr.port = 443

    # Duplicate port to test deduplication
    mock_conn4 = MagicMock()
    mock_conn4.status = "LISTEN"
    mock_conn4.laddr.port = 8080

    mock_connections = [mock_conn1, mock_conn2, mock_conn3, mock_conn4]
    mock_psutil.net_connections.return_value = mock_connections

    with patch("setup_diff.HAS_PSUTIL", True), patch(
        "setup_diff.psutil", mock_psutil, create=True
    ):
        ports = setup_diff.get_listening_ports()
        assert sorted(ports) == [8080, 9000]
        mock_psutil.net_connections.assert_called_once_with(kind="tcp")


def test_get_listening_ports_exception():
    mock_psutil = MagicMock()
    mock_psutil.net_connections.side_effect = Exception("psutil error")

    with patch("setup_diff.HAS_PSUTIL", True), patch(
        "setup_diff.psutil", mock_psutil, create=True
    ):
        assert setup_diff.get_listening_ports() == []


def test_generate_snapshot():
    mock_packages_json = json.dumps(
        [
            {"name": "pytest", "version": "8.2.2"},
            {"name": "requests", "version": "2.31.0"},
        ]
    )

    mock_completed_proc = MagicMock()
    mock_completed_proc.return_code = 0
    mock_completed_proc.returncode = 0
    mock_completed_proc.stdout = mock_packages_json

    with patch("platform.platform", return_value="TestOS-1.0"), patch(
        "sys.version", "3.12.2 (main)"
    ), patch("shutil.which", return_value="/mock/path"), patch(
        "subprocess.run", return_value=mock_completed_proc
    ), patch(
        "os.environ", {"PATH": "/usr/bin;/bin", "MY_VAR": "VAL"}
    ), patch(
        "setup_diff.get_listening_ports", return_value=[8080]
    ):

        snap = setup_diff.generate_snapshot()

        assert snap["os_platform"] == "TestOS-1.0"
        assert snap["python_version"] == "3.12.2 (main)"
        assert snap["binaries"]["git"] == "/mock/path"
        assert snap["environment_keys"] == ["MY_VAR", "PATH"]
        assert snap["packages"] == {"pytest": "8.2.2", "requests": "2.31.0"}
        assert (
            snap["path_entries"] == ["/usr/bin", "/bin"]
            if os.pathsep == ";"
            else ["/usr/bin;/bin"]
        )
        assert snap["listening_ports"] == [8080]


def test_compare_snapshots_match(capsys):
    snap_a = {
        "os_platform": "Windows-10",
        "python_version": "3.12.0\nDetail info",
        "binaries": {"git": "/usr/bin/git", "node": "/usr/bin/node"},
        "environment_keys": ["PATH", "USER"],
        "packages": {"pytest": "8.0"},
        "path_entries": ["/usr/bin"],
        "listening_ports": [8080],
    }
    # Identical
    snap_b = dict(snap_a)

    setup_diff.compare_snapshots(snap_a, snap_b)
    out, err = capsys.readouterr()

    assert "[+] Matches: Windows-10" in out
    assert "[+] Matches: 3.12.0" in out
    assert "[+] All common dev binaries have matching PATH lookups." in out
    assert "[+] Environment keys match exactly." in out
    assert "[+] Installed package configurations match." in out


def test_compare_snapshots_mismatch(capsys):
    snap_a = {
        "os_platform": "Windows-10",
        "python_version": "3.12.0\nDetail info",
        "binaries": {"git": "/usr/bin/git", "node": "/usr/bin/node"},
        "environment_keys": ["PATH", "USER", "ONLY_IN_A"],
        "packages": {"pytest": "8.0", "numpy": "1.2"},
        "path_entries": ["/usr/bin"],
        "listening_ports": [8080],
    }

    snap_b = {
        "os_platform": "Linux-Ubuntu",
        "python_version": "3.11.0\nDetail info",
        "binaries": {"git": "/usr/bin/git", "node": None},
        "environment_keys": ["PATH", "USER", "ONLY_IN_B"],
        "packages": {"pytest": "8.1", "pandas": "2.0"},
        "path_entries": ["/bin"],
        "listening_ports": [9000],
    }

    setup_diff.compare_snapshots(snap_a, snap_b)
    out, err = capsys.readouterr()

    assert "[!] MISMATCH:" in out
    assert "Machine A: Windows-10" in out
    assert "Machine B: Linux-Ubuntu" in out
    assert "Machine A: 3.12.0" in out
    assert "Machine B: 3.11.0" in out
    assert "Binary 'node'" in out
    assert "Machine A: /usr/bin/node" in out
    assert "Machine B: Not Found" in out
    assert "Missing on Machine B: ONLY_IN_A" in out
    assert "Missing on Machine A: ONLY_IN_B" in out
    assert "Found 3 mismatched packages" in out
    assert "pytest" in out
    assert "numpy" in out
    assert "pandas" in out


def raise_exit(code=0):
    raise SystemExit(code)


def test_main_default_command(capsys):
    snap = {"os_platform": "MockOS"}
    with patch("setup_diff.generate_snapshot", return_value=snap), patch(
        "sys.argv", ["setup_diff.py"]
    ):
        setup_diff.main()
        out, err = capsys.readouterr()
        assert "MockOS" in out


def test_main_snapshot_success():
    snap = {"os_platform": "MockOS"}
    mock_f = mock_open()
    with patch("setup_diff.generate_snapshot", return_value=snap), patch(
        "sys.argv", ["setup_diff.py", "snapshot", "output.json"]
    ), patch("builtins.open", mock_f):

        setup_diff.main()
        mock_f.assert_called_once_with(
            os.path.abspath("output.json"), "w", encoding="utf-8"
        )

        # Verify JSON dumping
        handle = mock_f()
        written_data = "".join(call.args[0] for call in handle.write.call_args_list)
        parsed_written = json.loads(written_data)
        assert parsed_written["os_platform"] == "MockOS"


def test_main_snapshot_failure():
    snap = {"os_platform": "MockOS"}
    with patch("setup_diff.generate_snapshot", return_value=snap), patch(
        "sys.argv", ["setup_diff.py", "snapshot", "output.json"]
    ), patch("builtins.open", side_effect=OSError("Permission denied")), patch(
        "sys.exit", side_effect=raise_exit
    ):

        with pytest.raises(SystemExit) as excinfo:
            setup_diff.main()
        assert excinfo.value.code == 1


def test_main_compare_success():
    snap_a = {"os_platform": "OS-A"}
    snap_b = {"os_platform": "OS-B"}

    def mock_file_open(path, *args, **kwargs):
        if "a.json" in path:
            return mock_open(read_data=json.dumps(snap_a))()
        if "b.json" in path:
            return mock_open(read_data=json.dumps(snap_b))()
        raise OSError("File not found")

    with patch("os.path.exists", return_value=True), patch(
        "sys.argv", ["setup_diff.py", "compare", "a.json", "b.json"]
    ), patch("builtins.open", side_effect=mock_file_open), patch(
        "setup_diff.compare_snapshots"
    ) as mock_compare:

        setup_diff.main()
        mock_compare.assert_called_once_with(snap_a, snap_b)


def test_main_compare_missing_files():
    with patch("os.path.exists", return_value=False), patch(
        "sys.argv", ["setup_diff.py", "compare", "a.json", "b.json"]
    ), patch("sys.exit", side_effect=raise_exit):

        with pytest.raises(SystemExit) as excinfo:
            setup_diff.main()
        assert excinfo.value.code == 1


def test_main_compare_invalid_json():
    with patch("os.path.exists", return_value=True), patch(
        "sys.argv", ["setup_diff.py", "compare", "a.json", "b.json"]
    ), patch("builtins.open", mock_open(read_data="invalid json")), patch(
        "sys.exit", side_effect=raise_exit
    ):

        with pytest.raises(SystemExit) as excinfo:
            setup_diff.main()
        assert excinfo.value.code == 1
