import os
import sys
import unittest
from datetime import datetime
from unittest.mock import MagicMock, patch

# Ensure config_archaeologist is importable
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
import config_archaeologist  # noqa: E402


class TestConfigArchaeologist(unittest.TestCase):

    @patch("os.environ.get")
    @patch("os.path.exists")
    @patch("os.path.isdir")
    @patch("os.listdir")
    def test_get_installed_programs_windows(
        self, mock_listdir, mock_isdir, mock_exists, mock_env_get
    ):
        # Setup mock environment variables
        def env_side_effect(key, default=None):
            env_vars = {
                "ProgramFiles": "C:\\Program Files",
                "ProgramFiles(x86)": "C:\\Program Files (x86)",
                "LOCALAPPDATA": "C:\\Users\\Mock\\AppData\\Local",
                "PATH": "C:\\MockBin" + os.pathsep + "C:\\InvalidPath",
            }
            return env_vars.get(key, default)

        mock_env_get.side_effect = env_side_effect

        # Setup exists and isdir
        def exists_side_effect(path):
            return path != "C:\\InvalidPath"

        mock_exists.side_effect = exists_side_effect
        mock_isdir.return_value = True

        # Setup listdir
        def listdir_side_effect(path):
            if path == "C:\\Program Files":
                return ["AppA", "AppB"]
            elif path == "C:\\Program Files (x86)":
                return ["AppC"]
            elif path == "C:\\Users\\Mock\\AppData\\Local\\Programs":
                return ["AppD"]
            elif path == "C:\\MockBin":
                return ["run.exe", "test.bat", "readme.txt", "no_ext"]
            return []

        mock_listdir.side_effect = listdir_side_effect

        programs = config_archaeologist.get_installed_programs_windows()
        expected = {"appa", "appb", "appc", "appd", "run", "test"}
        self.assertEqual(programs, expected)

    @patch("os.environ.get")
    @patch("os.path.exists")
    @patch("os.listdir")
    def test_get_installed_programs_unix(self, mock_listdir, mock_exists, mock_env_get):
        mock_env_get.return_value = (
            os.path.join("/mock", "bin") + os.pathsep + os.path.join("/invalid", "bin")
        )

        def exists_side_effect(path):
            return path in ["/usr/bin", "/bin", os.path.join("/mock", "bin")]

        mock_exists.side_effect = exists_side_effect

        def listdir_side_effect(path):
            if path == "/usr/bin":
                return ["bash", "LS"]
            elif path == "/bin":
                return ["sh"]
            elif path == os.path.join("/mock", "bin"):
                return ["python"]
            return []

        mock_listdir.side_effect = listdir_side_effect

        programs = config_archaeologist.get_installed_programs_unix()
        expected = {"bash", "ls", "sh", "python"}
        self.assertEqual(programs, expected)

    @patch("sys.platform", "win32")
    @patch("os.environ.get")
    def test_get_config_roots_windows(self, mock_env_get):
        def env_side_effect(key, default=None):
            env_vars = {"APPDATA": "C:\\Roaming", "LOCALAPPDATA": "C:\\Local"}
            return env_vars.get(key, default)

        mock_env_get.side_effect = env_side_effect

        roots = config_archaeologist.get_config_roots()
        self.assertEqual(
            roots, {"AppData Roaming": "C:\\Roaming", "AppData Local": "C:\\Local"}
        )

    @patch("sys.platform", "linux")
    @patch("os.path.expanduser")
    def test_get_config_roots_unix(self, mock_expanduser):
        mock_expanduser.return_value = "/home/user"
        roots = config_archaeologist.get_config_roots()
        self.assertEqual(
            roots,
            {
                "User Config": os.path.join("/home/user", ".config"),
                "User Local Share": os.path.join("/home/user", ".local", "share"),
            },
        )

    @patch("os.stat")
    @patch("os.walk")
    def test_get_folder_metrics(self, mock_walk, mock_stat):
        # Mock os.walk
        mock_walk.return_value = [("root_dir", [], ["file1.txt", "file2.txt"])]

        # Mock os.stat
        # First stat for root_dir, then files
        stat_root = MagicMock()
        stat_root.st_mtime = 1000000000.0

        stat_file1 = MagicMock()
        stat_file1.st_size = 500
        stat_file1.st_mtime = 1000000100.0

        stat_file2 = MagicMock()
        stat_file2.st_size = 1500
        stat_file2.st_mtime = 1000000200.0

        def stat_side_effect(path):
            if path == "root_dir":
                return stat_root
            elif path == os.path.join("root_dir", "file1.txt"):
                return stat_file1
            elif path == os.path.join("root_dir", "file2.txt"):
                return stat_file2
            raise OSError("Access denied")

        mock_stat.side_effect = stat_side_effect

        size, newest = config_archaeologist.get_folder_metrics("root_dir")
        self.assertEqual(size, 2000)
        self.assertEqual(newest, datetime.fromtimestamp(1000000200.0))

    @patch("sys.argv", ["config_archaeologist.py"])
    @patch("sys.platform", "win32")
    @patch("config_archaeologist.get_installed_programs_windows")
    @patch("config_archaeologist.get_config_roots")
    @patch("sys.exit")
    @patch("sys.stdout")
    def test_main_no_roots(
        self, mock_stdout, mock_exit, mock_get_roots, mock_get_programs
    ):
        mock_get_roots.return_value = {}
        mock_get_programs.return_value = set()
        mock_exit.side_effect = SystemExit(1)

        with self.assertRaises(SystemExit) as cm:
            config_archaeologist.main()
        self.assertEqual(cm.exception.code, 1)

    @patch("sys.argv", ["config_archaeologist.py"])
    @patch("sys.platform", "win32")
    @patch("config_archaeologist.get_installed_programs_windows")
    @patch("config_archaeologist.get_config_roots")
    @patch("os.path.exists")
    @patch("os.listdir")
    @patch("os.path.isdir")
    @patch("config_archaeologist.get_folder_metrics")
    @patch("sys.exit")
    @patch("config_archaeologist.datetime")
    def test_main_no_candidates(
        self,
        mock_datetime,
        mock_exit,
        mock_metrics,
        mock_isdir,
        mock_listdir,
        mock_exists,
        mock_get_roots,
        mock_get_programs,
    ):
        mock_get_programs.return_value = {"appa"}
        mock_get_roots.return_value = {"Local": "/mock/local"}
        mock_exists.return_value = True
        mock_listdir.return_value = ["microsoft", "AppA"]

        def isdir_side_effect(path):
            return True

        mock_isdir.side_effect = isdir_side_effect

        now = datetime(2026, 7, 19, 12, 0, 0)
        mock_datetime.now.return_value = now
        mock_datetime.min = datetime.min

        # AppA metrics: size = 100, updated now (age = 0)
        # Confidence = 0 (active program "appa", active timestamp, non-zero size)
        mock_metrics.return_value = (100, now)
        mock_exit.side_effect = SystemExit(0)

        with self.assertRaises(SystemExit) as cm:
            config_archaeologist.main()
        self.assertEqual(cm.exception.code, 0)

    @patch("sys.argv", ["config_archaeologist.py"])
    @patch("sys.platform", "win32")
    @patch("config_archaeologist.get_installed_programs_windows")
    @patch("config_archaeologist.get_config_roots")
    @patch("os.path.exists")
    @patch("os.listdir")
    @patch("os.path.isdir")
    @patch("config_archaeologist.get_folder_metrics")
    @patch("config_archaeologist.datetime")
    @patch("sys.exit")
    def test_main_with_candidates(
        self,
        mock_exit,
        mock_datetime,
        mock_metrics,
        mock_isdir,
        mock_listdir,
        mock_exists,
        mock_get_roots,
        mock_get_programs,
    ):
        mock_get_programs.return_value = {"appa"}
        mock_get_roots.return_value = {"Local": "/mock/local"}
        mock_exists.return_value = True
        mock_listdir.return_value = ["AppB"]
        mock_isdir.return_value = True

        now = datetime(2026, 7, 19, 12, 0, 0)
        mock_datetime.now.return_value = now
        mock_datetime.min = datetime.min

        # AppB is not in programs (score +60)
        # Size = 0 (score +10)
        # Last active is datetime.min (score +20)
        # Total score = 90 (>= 50 confidence) -> candidate!
        mock_metrics.return_value = (0, datetime.min)

        # sys.exit should not be called with 0 because candidates are printed
        config_archaeologist.main()
        mock_exit.assert_not_called()


if __name__ == "__main__":
    unittest.main()
