import os
import stat
import sys
from unittest.mock import MagicMock, patch

# Add target directory to sys.path so we can import permission_explainer
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
import permission_explainer  # noqa: E402


def test_get_current_user_unix_success():
    with patch("getpass.getuser", return_value="testuser"), patch(
        "os.getuid", return_value=1000, create=True
    ), patch("os.getgroups", return_value=[1000, 4], create=True):
        username, uid, gids = permission_explainer.get_current_user_unix()
        assert username == "testuser"
        assert uid == 1000
        assert gids == [1000, 4]


def test_get_current_user_unix_attribute_error():
    with patch("getpass.getuser", return_value="testuser"), patch(
        "os.getuid", side_effect=AttributeError, create=True
    ):
        username, uid, gids = permission_explainer.get_current_user_unix()
        assert username == "testuser"
        assert uid == 0
        assert gids == []


def test_explain_unix_permissions_oserror():
    with patch("os.stat", side_effect=OSError("No such file or directory")):
        expl, fix = permission_explainer.explain_unix_permissions(
            "nonexistent", "read", "testuser"
        )
        assert "Error: Cannot access path" in expl
        assert fix == ""


def test_explain_unix_permissions_owner_allowed():
    # Owner UID 1000, Mode: owner read/write (0o600)
    mock_stat = MagicMock()
    mock_stat.st_mode = stat.S_IFREG | 0o600
    mock_stat.st_uid = 1000
    mock_stat.st_gid = 1000

    with patch("os.stat", return_value=mock_stat), patch(
        "permission_explainer.get_current_user_unix",
        return_value=("testuser", 1000, [1000]),
    ):

        expl, fix = permission_explainer.explain_unix_permissions(
            "file.txt", "read", "testuser"
        )
        assert "Active user 'testuser' is the OWNER" in expl
        assert "Access is theoretically ALLOWED" in expl
        assert fix == ""


def test_explain_unix_permissions_owner_denied_write():
    # Owner UID 1000, Mode: owner read only (0o400)
    mock_stat = MagicMock()
    mock_stat.st_mode = stat.S_IFREG | 0o400
    mock_stat.st_uid = 1000
    mock_stat.st_gid = 1000

    with patch("os.stat", return_value=mock_stat), patch(
        "permission_explainer.get_current_user_unix",
        return_value=("testuser", 1000, [1000]),
    ):

        expl, fix = permission_explainer.explain_unix_permissions(
            "file.txt", "write", "testuser"
        )
        assert "Active user 'testuser' is the OWNER" in expl
        assert "Access denied" in expl
        assert fix == 'chmod u+w "file.txt"'


def test_explain_unix_permissions_owner_denied_write_directory():
    # Owner UID 1000, Mode: owner read only directory (stat.S_IFDIR | 0o400)
    mock_stat = MagicMock()
    mock_stat.st_mode = stat.S_IFDIR | 0o400
    mock_stat.st_uid = 1000
    mock_stat.st_gid = 1000

    with patch("os.stat", return_value=mock_stat), patch(
        "permission_explainer.get_current_user_unix",
        return_value=("testuser", 1000, [1000]),
    ):

        expl, fix = permission_explainer.explain_unix_permissions(
            "dir", "write", "testuser"
        )
        assert "Active user 'testuser' is the OWNER" in expl
        assert "Access denied" in expl
        assert fix == 'chmod u+w -R "dir"'


def test_explain_unix_permissions_group_denied_read():
    # Owner UID 9999, GID 1000, Mode: group has no read/write, others none (0o700)
    mock_stat = MagicMock()
    mock_stat.st_mode = stat.S_IFREG | 0o700
    mock_stat.st_uid = 9999
    mock_stat.st_gid = 1000

    with patch("os.stat", return_value=mock_stat), patch(
        "permission_explainer.get_current_user_unix",
        return_value=("testuser", 1000, [1000]),
    ):

        expl, fix = permission_explainer.explain_unix_permissions(
            "file.txt", "read", "testuser"
        )
        assert "belongs to the GROUP" in expl
        assert "Access denied" in expl
        assert fix == 'sudo chown "testuser" "file.txt" OR chmod o+r "file.txt"'


def test_explain_unix_permissions_other_denied_execute():
    # Owner UID 9999, GID 9999, Mode: owner rwx (0o700)
    mock_stat = MagicMock()
    mock_stat.st_mode = stat.S_IFREG | 0o700
    mock_stat.st_uid = 9999
    mock_stat.st_gid = 9999

    with patch("os.stat", return_value=mock_stat), patch(
        "permission_explainer.get_current_user_unix",
        return_value=("testuser", 1000, [1000]),
    ):

        expl, fix = permission_explainer.explain_unix_permissions(
            "file.txt", "execute", "testuser"
        )
        assert "classified as OTHER" in expl
        assert "Access denied" in expl
        assert fix == 'sudo chown "testuser" "file.txt" OR chmod o+x "file.txt"'


def test_explain_windows_permissions_oserror():
    with patch("os.stat", side_effect=OSError("Access denied")):
        expl, fix = permission_explainer.explain_windows_permissions(
            "file.txt", "write", "testuser"
        )
        assert "Error: Cannot access path" in expl
        assert fix == ""


def test_explain_windows_permissions_readonly_write():
    # stat.S_IWRITE is not set -> read-only
    mock_stat = MagicMock()
    mock_stat.st_mode = 0

    mock_sub_run = MagicMock()
    mock_sub_run.stdout = "file.txt testuser:(R)"

    with patch("os.stat", return_value=mock_stat), patch(
        "subprocess.run", return_value=mock_sub_run
    ):

        expl, fix = permission_explainer.explain_windows_permissions(
            "file.txt", "write", "testuser"
        )
        assert "marked as READ-ONLY" in expl
        assert 'attrib -R "file.txt"' in fix
        assert 'icacls "file.txt" /grant "testuser":W' in fix


def test_explain_windows_permissions_allowed_read():
    mock_stat = MagicMock()
    mock_stat.st_mode = stat.S_IWRITE

    mock_sub_run = MagicMock()
    mock_sub_run.stdout = "file.txt testuser:(R)"

    with patch("os.stat", return_value=mock_stat), patch(
        "subprocess.run", return_value=mock_sub_run
    ):

        expl, fix = permission_explainer.explain_windows_permissions(
            "file.txt", "read", "testuser"
        )
        assert "NTFS matching permissions for user 'testuser': R" in expl
        assert fix == 'icacls "file.txt" /grant "testuser":R'


def test_explain_windows_permissions_subprocess_error():
    mock_stat = MagicMock()
    mock_stat.st_mode = stat.S_IWRITE

    with patch("os.stat", return_value=mock_stat), patch(
        "subprocess.run", side_effect=OSError("icacls not found")
    ):

        expl, fix = permission_explainer.explain_windows_permissions(
            "file.txt", "execute", "testuser"
        )
        assert "Could not run icacls utility" in expl
        assert fix == 'icacls "file.txt" /grant "testuser":RX'


def test_main_path_not_exists():
    with patch("argparse.ArgumentParser.parse_args") as mock_args, patch(
        "os.path.exists", return_value=False
    ), patch("sys.exit") as mock_exit:

        mock_args.return_value = MagicMock(
            path="nonexistent", operation="read", user=None
        )
        permission_explainer.main()
        mock_exit.assert_called_once_with(1)


def test_main_win32_success():
    with patch("argparse.ArgumentParser.parse_args") as mock_args, patch(
        "os.path.exists", return_value=True
    ), patch("getpass.getuser", return_value="testuser"), patch(
        "sys.platform", "win32"
    ), patch(
        "permission_explainer.explain_windows_permissions",
        return_value=("Win Expl", "Win Fix"),
    ) as mock_win:

        mock_args.return_value = MagicMock(
            path="file.txt", operation="write", user="testuser"
        )
        permission_explainer.main()
        mock_win.assert_called_once_with("file.txt", "write", "testuser")


def test_main_unix_success():
    with patch("argparse.ArgumentParser.parse_args") as mock_args, patch(
        "os.path.exists", return_value=True
    ), patch("getpass.getuser", return_value="testuser"), patch(
        "sys.platform", "linux"
    ), patch(
        "permission_explainer.explain_unix_permissions",
        return_value=("Unix Expl", "Unix Fix"),
    ) as mock_unix:

        mock_args.return_value = MagicMock(
            path="file.txt", operation="write", user="testuser"
        )
        permission_explainer.main()
        mock_unix.assert_called_once_with("file.txt", "write", "testuser")
