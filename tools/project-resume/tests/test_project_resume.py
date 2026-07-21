import json
import os
import sys
from unittest.mock import MagicMock, patch

import pytest

# Add target directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
import project_resume  # noqa: E402


def test_get_project_description_readme(tmp_path):
    readme = tmp_path / "README.md"
    readme.write_text(
        "# Project Header\n\nFirst paragraph of text.\nSecond paragraph.\n"
        "Third paragraph.\nFourth paragraph."
    )

    desc = project_resume.get_project_description(str(tmp_path))
    assert "First paragraph of text. Second paragraph. Third paragraph." in desc


def test_get_project_description_package_json(tmp_path):
    p_json = tmp_path / "package.json"
    p_json.write_text(json.dumps({"description": "Test NodeJS Project"}))

    desc = project_resume.get_project_description(str(tmp_path))
    assert "NodeJS project: Test NodeJS Project" in desc


def test_get_project_description_fallback(tmp_path):
    desc = project_resume.get_project_description(str(tmp_path))
    assert "No description found" in desc


def test_get_git_history_no_git(tmp_path):
    history = project_resume.get_git_history(str(tmp_path))
    assert "No Git repository history detected." in history[0]


def test_get_git_history_with_git(tmp_path):
    git_dir = tmp_path / ".git"
    git_dir.mkdir()

    mock_branch = MagicMock(stdout="main\n", returncode=0)
    mock_status = MagicMock(stdout=" M file1.py\n?? untracked.py\n", returncode=0)
    mock_log = MagicMock(stdout="abc1234 Commit message\n", returncode=0)
    mock_reflog = MagicMock(stdout="abc1234 HEAD@{0}: commit: message\n", returncode=0)

    def side_effect(cmd, **kwargs):
        if "branch" in cmd:
            return mock_branch
        if "status" in cmd:
            return mock_status
        if "log" in cmd:
            return mock_log
        if "reflog" in cmd:
            return mock_reflog
        return MagicMock(stdout="", returncode=0)

    with patch("subprocess.run", side_effect=side_effect):
        history = project_resume.get_git_history(str(tmp_path))
        assert "Active Branch: main" in history
        assert "Dirty/untracked files (2):" in history
        assert "  - M file1.py" in history
        assert "  - ?? untracked.py" in history
        assert "Recent Commits:" in history
        assert "  - abc1234 Commit message" in history
        assert "Last Git Operations:" in history
        assert "  - abc1234 HEAD@{0}: commit: message" in history


def test_get_git_history_with_git_dirty_limit(tmp_path):
    git_dir = tmp_path / ".git"
    git_dir.mkdir()

    stdout = "\n".join([f" M file{i}.py" for i in range(1, 8)]) + "\n"
    mock_status = MagicMock(stdout=stdout, returncode=0)

    with patch("subprocess.run", return_value=mock_status):
        history = project_resume.get_git_history(str(tmp_path))
        assert "Dirty/untracked files (7):" in history
        assert "  ... and 2 more files." in history


def test_get_git_history_exception(tmp_path):
    git_dir = tmp_path / ".git"
    git_dir.mkdir()

    with patch("subprocess.run", side_effect=OSError("Git command failed")):
        history = project_resume.get_git_history(str(tmp_path))
        assert "Could not retrieve Git logs: Git command failed" in history[0]


def test_scan_todos(tmp_path):
    py_file = tmp_path / "app.py"
    py_file.write_text(
        "# TODO: fix this bug\n# FIXME: critical issue\n# normal comment"
    )

    js_file = tmp_path / "index.js"
    js_file.write_text("// BUG: check memory leak\n// normal code")

    ignored_dir = tmp_path / "node_modules"
    ignored_dir.mkdir()
    ignored_file = ignored_dir / "index.js"
    ignored_file.write_text("// TODO: ignore me")

    unsupported_file = tmp_path / "notes.txt"
    unsupported_file.write_text("TODO: text files shouldn't be scanned")

    todos = project_resume.scan_todos(str(tmp_path))
    assert len(todos) == 3

    paths = [t[0] for t in todos]
    assert "app.py" in paths
    assert "index.js" in paths
    assert "node_modules/index.js" not in paths
    assert "notes.txt" not in paths

    details = [t[2] for t in todos]
    assert "TODO: fix this bug" in details
    assert "FIXME: critical issue" in details
    assert "BUG: check memory leak" in details


def test_get_execution_commands_node(tmp_path):
    p_json = tmp_path / "package.json"
    p_json.write_text("{}")
    cmds = project_resume.get_execution_commands(str(tmp_path))
    assert "Node.js package detected:" in cmds


def test_get_execution_commands_python(tmp_path):
    manage_py = tmp_path / "manage.py"
    manage_py.write_text("")
    cmds = project_resume.get_execution_commands(str(tmp_path))
    assert "Python project detected:" in cmds
    assert "  - python manage.py runserver (Django server)" in cmds

    os.remove(manage_py)
    app_py = tmp_path / "app.py"
    app_py.write_text("")
    cmds = project_resume.get_execution_commands(str(tmp_path))
    assert "  - python app.py (Execute main application entry)" in cmds


def test_get_execution_commands_rust(tmp_path):
    cargo = tmp_path / "Cargo.toml"
    cargo.write_text("")
    cmds = project_resume.get_execution_commands(str(tmp_path))
    assert "Rust Cargo project detected:" in cmds


def test_check_broken_dependencies_no_reqs(tmp_path):
    broken = project_resume.check_broken_dependencies(str(tmp_path))
    assert broken == []


def test_check_broken_dependencies_parse(tmp_path):
    reqs = tmp_path / "requirements.txt"
    reqs.write_text(
        "pytest>=7.0.0\n# comment\nrequests==2.28.1\n-r other.txt\n"
        "./localpkg\nmissing-library"
    )

    def mock_find_spec(name):
        if name in ("pytest", "requests"):
            return MagicMock()
        return None

    with patch("importlib.util.find_spec", side_effect=mock_find_spec):
        broken = project_resume.check_broken_dependencies(str(tmp_path))
        assert broken == ["missing-library"]


def test_find_entry_points(tmp_path):
    main_py = tmp_path / "main.py"
    main_py.write_text("")

    other_py = tmp_path / "other.py"
    other_py.write_text("if __name__ == '__main__':\n    pass")

    index_js = tmp_path / "index.js"
    index_js.write_text("")

    entries = project_resume.find_entry_points(str(tmp_path))
    assert len(entries) == 3
    paths = [e.split(" ")[0] for e in entries]
    assert "main.py" in paths
    assert "other.py" in paths
    assert "index.js" in paths


def test_main_directory_not_found(capsys):
    with patch("sys.argv", ["project_resume.py", "nonexistent_dir"]), pytest.raises(
        SystemExit
    ) as exc_info:
        project_resume.main()

    assert exc_info.value.code == 1
    captured = capsys.readouterr()
    assert "Path does not exist" in captured.err


def test_main_success(tmp_path, capsys):
    readme = tmp_path / "README.md"
    readme.write_text("# Project\nThis is a sample project description.")

    main_py = tmp_path / "main.py"
    main_py.write_text("if __name__ == '__main__': pass\n# TODO: Task 1")

    reqs = tmp_path / "requirements.txt"
    reqs.write_text("mypackage")

    with patch("sys.argv", ["project_resume.py", str(tmp_path)]), patch(
        "importlib.util.find_spec", return_value=None
    ):
        project_resume.main()

        captured = capsys.readouterr()
        assert "PROJECT RESUME DIAGNOSTIC AUDIT" in captured.out
        assert "This is a sample project description." in captured.out
        assert "main.py" in captured.out
        assert "Python project detected:" in captured.out
        assert "Missing/uninstalled requirements found" in captured.out
        assert "mypackage" in captured.out
        assert "TODO: Task 1" in captured.out
        assert "SUGGESTED NEXT STEPS:" in captured.out
