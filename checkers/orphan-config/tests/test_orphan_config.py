import os
import sys
from unittest.mock import patch

# Add target directory to sys.path so we can import orphan_config
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
import orphan_config  # noqa: E402


def test_get_common_app_paths_win32():
    with patch("sys.platform", "win32"), patch("os.environ.get") as mock_get:
        mock_get.side_effect = lambda var: {
            "ProgramFiles": "C:\\Program Files",
            "ProgramFiles(x86)": "C:\\Program Files (x86)",
            "LocalAppData": "C:\\Users\\test\\AppData\\Local",
        }.get(var)

        paths = orphan_config.get_common_app_paths()
        assert "C:\\Program Files" in paths
        assert "C:\\Program Files (x86)" in paths
        assert "C:\\Users\\test\\AppData\\Local" in paths
        assert len(paths) == 3


def test_get_common_app_paths_darwin():
    with patch("sys.platform", "darwin"):
        paths = orphan_config.get_common_app_paths()
        assert "/Applications" in paths
        assert "/usr/local/bin" in paths
        assert len(paths) == 2


def test_get_common_app_paths_linux():
    with patch("sys.platform", "linux"):
        paths = orphan_config.get_common_app_paths()
        assert "/usr/bin" in paths
        assert "/usr/local/bin" in paths
        assert "/opt" in paths
        assert len(paths) == 3


def test_verify_active_binary_path_match():
    with patch("shutil.which", return_value="/usr/bin/my_app"):
        assert orphan_config.verify_active_binary("my_app", ["/opt"]) is True


def test_verify_active_binary_win32_exe():
    with patch("sys.platform", "win32"), patch("shutil.which") as mock_which:
        # First call is for raw name (returns None), second is for exe
        mock_which.side_effect = lambda x: (
            "C:\\Windows\\system32\\my_app.exe" if x.endswith(".exe") else None
        )
        assert orphan_config.verify_active_binary("my_app", ["/opt"]) is True


def test_verify_active_binary_dir_check():
    with patch("shutil.which", return_value=None), patch(
        "os.path.exists", return_value=True
    ), patch("os.listdir", return_value=["MyAppDirectory", "OtherDir"]):
        assert orphan_config.verify_active_binary("myapp", ["/opt"]) is True


def test_verify_active_binary_not_found():
    with patch("shutil.which", return_value=None), patch(
        "os.path.exists", return_value=True
    ), patch("os.listdir", return_value=["OtherDir"]):
        assert orphan_config.verify_active_binary("myapp", ["/opt"]) is False


def test_get_dir_size():
    mock_walk_data = [
        ("/fake/dir", ["subdir"], ["file1.txt", "file2.txt"]),
        ("/fake/dir/subdir", [], ["file3.txt"]),
    ]
    sizes = {
        os.path.join("/fake/dir", "file1.txt"): 100,
        os.path.join("/fake/dir", "file2.txt"): 200,
        os.path.join("/fake/dir/subdir", "file3.txt"): 300,
    }
    with patch("os.walk", return_value=mock_walk_data), patch(
        "os.path.getsize", side_effect=lambda x: sizes[x]
    ):
        total_size = orphan_config.get_dir_size("/fake/dir")
        assert total_size == 600


def test_main_no_orphans():
    with patch("argparse.ArgumentParser.parse_args"), patch(
        "os.path.expanduser", return_value="/home/user"
    ), patch("sys.platform", "linux"), patch(
        "os.path.exists", return_value=True
    ), patch(
        "os.listdir", return_value=["my_active_app", ".hidden_config"]
    ), patch(
        "os.path.isdir", return_value=True
    ), patch(
        "orphan_config.verify_active_binary", return_value=True
    ), patch(
        "sys.exit"
    ) as mock_exit:

        orphan_config.main()
        mock_exit.assert_called_once_with(0)


def test_main_with_orphans():
    with patch("argparse.ArgumentParser.parse_args"), patch(
        "os.path.expanduser", return_value="/home/user"
    ), patch("sys.platform", "linux"), patch(
        "os.path.exists", return_value=True
    ), patch(
        "os.listdir", return_value=["my_active_app", "my_orphan_app", "temp", "Git"]
    ), patch(
        "os.path.isdir",
        side_effect=lambda x: (
            True
            if os.path.basename(x) in ["my_active_app", "my_orphan_app", "temp", "Git"]
            else False
        ),
    ), patch(
        "orphan_config.verify_active_binary"
    ) as mock_verify, patch(
        "orphan_config.get_dir_size", return_value=1048576 * 5
    ), patch(
        "sys.exit"
    ) as mock_exit:

        # my_active_app is verified active; my_orphan_app is not
        mock_verify.side_effect = lambda name, app_paths: (
            True if name == "my_active_app" else False
        )

        orphan_config.main()
        mock_exit.assert_not_called()
