import os
import sys
from io import StringIO
from unittest.mock import MagicMock, mock_open, patch

import pytest

# Add parent directory to sys.path to import commit_surgeon
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
import commit_surgeon  # noqa: E402


def test_is_git_repo_true():
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0)
        assert commit_surgeon.is_git_repo("dummy_path") is True
        mock_run.assert_called_once_with(
            ["git", "rev-parse", "--is-inside-work-tree"],
            cwd="dummy_path",
            stdout=-1,
            stderr=-1,
            text=True,
            check=False,
        )


def test_is_git_repo_false():
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=128)
        assert commit_surgeon.is_git_repo("dummy_path") is False

    with patch("subprocess.run", side_effect=OSError):
        assert commit_surgeon.is_git_repo("dummy_path") is False


def test_get_modified_files():
    porcelain_output = (
        " M file1.py\n"
        "R  old_file.js -> new_file.js\n"
        "?? untracked.py\n"
        " D deleted.py\n"
    )
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout=porcelain_output)
        files = commit_surgeon.get_modified_files("dummy_path")
        assert files == ["file1.py", "new_file.js", "untracked.py", "deleted.py"]


def test_get_modified_files_error():
    with patch("subprocess.run", side_effect=OSError):
        assert commit_surgeon.get_modified_files("dummy_path") == []


def test_extract_imports_nonexistent():
    with patch("os.path.exists", return_value=False):
        assert commit_surgeon.extract_imports("some_file.py") == set()


def test_extract_imports_python():
    file_content = (
        "import os\n"
        "from sys import argv\n"
        "import helper.utils as utils\n"
        "  import indent_mod\n"
    )
    with patch("os.path.exists", return_value=True), patch(
        "builtins.open", mock_open(read_data=file_content)
    ):
        imports = commit_surgeon.extract_imports("file.py")
        assert "os" in imports
        assert "sys" in imports
        assert "helper" in imports
        assert "indent_mod" in imports


def test_extract_imports_js():
    file_content = (
        "import 'react-dom';\n" "require('path');\n" "import './local-helper';\n"
    )
    with patch("os.path.exists", return_value=True), patch(
        "builtins.open", mock_open(read_data=file_content)
    ):
        imports = commit_surgeon.extract_imports("file.js")
        assert "react-dom" in imports
        assert "path" in imports
        assert "local-helper" in imports


def test_map_dependencies():
    modified_files = ["app.py", "helper.py", "db.py"]

    def mock_extract_imports(file_path):
        if "app.py" in file_path:
            return {"helper", "os"}
        if "helper.py" in file_path:
            return {"db"}
        if "db.py" in file_path:
            return {"sys"}
        return set()

    with patch("commit_surgeon.extract_imports", side_effect=mock_extract_imports):
        deps = commit_surgeon.map_dependencies("/dummy", modified_files)
        assert deps["app.py"] == {"helper.py"}
        assert deps["helper.py"] == {"db.py"}
        assert deps["db.py"] == set()


def test_main_path_not_exists():
    with patch("os.path.exists", return_value=False), patch(
        "sys.argv", ["commit_surgeon.py", "/nonexistent"]
    ), pytest.raises(SystemExit) as excinfo:
        commit_surgeon.main()
    assert excinfo.value.code == 1


def test_main_not_git_repo():
    with patch("os.path.exists", return_value=True), patch(
        "commit_surgeon.is_git_repo", return_value=False
    ), patch("sys.argv", ["commit_surgeon.py"]), pytest.raises(SystemExit) as excinfo:
        commit_surgeon.main()
    assert excinfo.value.code == 1


def test_main_clean_tree():
    with patch("os.path.exists", return_value=True), patch(
        "commit_surgeon.is_git_repo", return_value=True
    ), patch("commit_surgeon.get_modified_files", return_value=[]), patch(
        "sys.argv", ["commit_surgeon.py"]
    ), pytest.raises(
        SystemExit
    ) as excinfo:
        commit_surgeon.main()
    assert excinfo.value.code == 0


def test_main_dirty_tree():
    modified = [
        "requirements.txt",
        "README.md",
        "db.py",
        "helper.py",
        "app.py",
        "test_app.py",
    ]

    def mock_extract_imports(file_path):
        if "app.py" in file_path:
            return {"helper"}
        if "helper.py" in file_path:
            return {"db"}
        return set()

    with patch("os.path.exists", return_value=True), patch(
        "commit_surgeon.is_git_repo", return_value=True
    ), patch("commit_surgeon.get_modified_files", return_value=modified), patch(
        "commit_surgeon.extract_imports", side_effect=mock_extract_imports
    ), patch(
        "sys.argv", ["commit_surgeon.py"]
    ):
        new_stdout = StringIO()
        with patch("sys.stdout", new_stdout):
            commit_surgeon.main()

        output = new_stdout.getvalue()
        assert "SUGGESTED COMMIT GROUPS" in output
        assert "requirements.txt" in output
        assert "README.md" in output
        assert "db.py" in output
        assert "app.py" in output
        assert "test_app.py" in output
