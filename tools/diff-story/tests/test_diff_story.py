import gettext
import os
import subprocess
import sys
from unittest.mock import MagicMock, mock_open, patch

import pytest

# Add path to tools/diff-story to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from diff_story import get_git_diff, main, parse_diff_contents  # noqa: E402


@pytest.fixture(autouse=True)
def _stub_gettext_catalog():
    """Stub gettext catalog loading so argparse never opens files via mocked open()."""
    with patch(
        "gettext.translation", lambda *args, **kwargs: gettext.NullTranslations()
    ):
        yield


def test_get_git_diff_success():
    mock_res = MagicMock()
    mock_res.returncode = 0
    mock_res.stdout = "diff contents"
    with patch("subprocess.run", return_value=mock_res) as mock_run:
        res = get_git_diff("/fake/path")
        assert res == "diff contents"
        mock_run.assert_called_once_with(
            ["git", "diff", "HEAD"],
            cwd="/fake/path",
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )


def test_get_git_diff_empty():
    mock_res = MagicMock()
    mock_res.returncode = 0
    mock_res.stdout = "   "
    with patch("subprocess.run", return_value=mock_res):
        assert get_git_diff("/fake/path") is None


def test_get_git_diff_failure():
    mock_res = MagicMock()
    mock_res.returncode = 1
    with patch("subprocess.run", return_value=mock_res):
        assert get_git_diff("/fake/path") is None


def test_get_git_diff_exception():
    with patch("subprocess.run", side_effect=OSError("binary not found")):
        assert get_git_diff("/fake/path") is None


def test_parse_diff_contents_empty():
    res = parse_diff_contents("")
    assert res == {
        "files_count": 0,
        "additions": 0,
        "deletions": 0,
        "dependencies": [],
        "configs": [],
        "refactors": [],
        "risks": [],
        "behavioral": [],
    }


def test_parse_diff_contents_dependencies():
    diff_text = """diff --git a/requirements.txt b/requirements.txt
--- a/requirements.txt
+++ b/requirements.txt
@@ -1,1 +1,2 @@
+requests==2.31.0
+beautifulsoup4
diff --git a/src/app.py b/src/app.py
--- a/src/app.py
+++ b/src/app.py
+import sys
+from os import path
"""
    res = parse_diff_contents(diff_text)
    assert res["files_count"] == 2
    assert "requirements.txt" in res["dependencies"]
    assert "src/app.py" in res["dependencies"]
    assert res["additions"] == 4
    assert "src/app.py" not in res["behavioral"]


def test_parse_diff_contents_configs():
    diff_text = """diff --git a/config.json b/config.json
--- a/config.json
+++ b/config.json
+  "port": 8080
diff --git a/app.js b/app.js
--- a/app.js
+++ b/app.js
+const timeout = 5000;
"""
    res = parse_diff_contents(diff_text)
    assert "config.json" in res["configs"]
    assert "app.js" in res["configs"]
    assert "app.js" in res["behavioral"]


def test_parse_diff_contents_refactors():
    diff_text = """diff --git a/src/calc.py b/src/calc.py
--- a/src/calc.py
+++ b/src/calc.py
-def old_add(a, b):
+def add(a, b):
diff --git a/src/utils.py b/src/utils.py
--- a/src/utils.py
+++ b/src/utils.py
+# Refactor utilities helper
"""
    res = parse_diff_contents(diff_text)
    assert "src/calc.py" in res["refactors"]
    assert "src/utils.py" in res["refactors"]
    assert "src/calc.py" not in res["behavioral"]
    assert "src/utils.py" not in res["behavioral"]


def test_parse_diff_contents_risks_sensitive():
    diff_text = """diff --git a/auth.js b/auth.js
--- a/auth.js
+++ b/auth.js
+const pass = "secret";
"""
    res = parse_diff_contents(diff_text)
    assert len(res["risks"]) == 1
    assert res["risks"][0] == (
        "auth.js",
        "Modifications touch security/auth or credentials domains",
    )


def test_parse_diff_contents_risks_volume():
    additions = "\n".join([f"+ line {i}" for i in range(151)])
    diff_text = f"""diff --git a/large.py b/large.py
--- a/large.py
+++ b/large.py
{additions}
"""
    res = parse_diff_contents(diff_text)
    assert len(res["risks"]) == 1
    assert res["risks"][0] == (
        "large.py",
        "High volume edits (Added: 151, Deleted: 0)",
    )


def test_main_file_not_found(capsys):
    with patch("os.path.exists", return_value=False), patch(
        "sys.argv", ["diff_story.py", "missing.diff"]
    ):
        try:
            main()
        except SystemExit as exc:
            assert exc.code == 1
    captured = capsys.readouterr()
    assert "Error: Diff file not found" in captured.err


def test_main_file_read_error(capsys):
    with patch("os.path.exists", return_value=True), patch(
        "builtins.open", side_effect=OSError("Permission denied")
    ), patch("sys.argv", ["diff_story.py", "exist.diff"]):
        try:
            main()
        except SystemExit as exc:
            assert exc.code == 1
    captured = capsys.readouterr()
    assert "Error reading diff file: Permission denied" in captured.err


def test_main_fallback_git_diff_success(capsys):
    with patch("sys.argv", ["diff_story.py"]), patch(
        "diff_story.get_git_diff", return_value="diff --git a/a.py b/a.py\n+import os"
    ):
        main()
    captured = capsys.readouterr()
    assert "FILES IMPACTED: 1" in captured.out
    assert "DEPENDENCY CHANGES:" in captured.out
    assert "- a.py" in captured.out


def test_main_fallback_git_diff_failure(capsys):
    with patch("sys.argv", ["diff_story.py"]), patch(
        "diff_story.get_git_diff", return_value=None
    ):
        try:
            main()
        except SystemExit as exc:
            assert exc.code == 1
    captured = capsys.readouterr()
    assert "Error: No active Git changes found" in captured.err


def test_main_file_read_success(capsys):
    diff_data = """diff --git a/config.yaml b/config.yaml
--- a/config.yaml
+++ b/config.yaml
+port: 9000
"""
    with patch("os.path.exists", return_value=True), patch(
        "builtins.open", mock_open(read_data=diff_data)
    ), patch("sys.argv", ["diff_story.py", "some.diff"]):
        main()
    captured = capsys.readouterr()
    assert "FILES IMPACTED: 1" in captured.out
    assert "CONFIGURATION EDITS:" in captured.out
    assert "- config.yaml" in captured.out
