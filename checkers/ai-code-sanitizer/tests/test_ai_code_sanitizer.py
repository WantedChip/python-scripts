"""Unit tests for ai_code_sanitizer.py."""

import sys
from pathlib import Path
from unittest.mock import patch

import pytest

# Add import injection to resolve checkers package
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# pylint: disable=import-error, wrong-import-position
import ai_code_sanitizer  # noqa: E402


def test_check_fake_imports(tmp_path: Path) -> None:
    """Test fake or unresolvable imports scanning."""
    code = """
import os
import non_existent_package_1234
from math import sin, non_existent_api
"""
    file_path = tmp_path / "test_file.py"
    file_path.write_text(code, encoding="utf-8")
    tree = ai_code_sanitizer.ast.parse(code)
    findings = ai_code_sanitizer.check_fake_imports(tree, file_path)

    # non_existent_package_1234 should be flagged
    assert any("non_existent_package_1234" in f[1] for f in findings)
    # math.sin is valid, but math.non_existent_api is not
    assert any("non_existent_api" in f[1] for f in findings)
    # os is standard, so no warnings about it
    assert not any("os" in f[1] for f in findings)


def test_check_duplicate_helpers() -> None:
    """Test identification of duplicate helper functions."""
    code = """
def helper_one(x):
    y = x + 1
    return y * 2

def helper_two(x):
    y = x + 1
    return y * 2

def helper_three(x):
    return x * 10
"""
    tree = ai_code_sanitizer.ast.parse(code)
    findings = ai_code_sanitizer.check_duplicate_helpers(tree)

    # helper_two is functionally identical to helper_one
    assert any("helper_two" in f[1] and "helper_one" in f[1] for f in findings)


def test_check_placeholder_comments() -> None:
    """Test detection of development placeholders."""
    lines = [
        "def run():",
        "    # TODO: implement here",
        "    pass  # placeholder",
        "    # normal comment",
    ]
    findings = ai_code_sanitizer.check_placeholder_comments(lines)

    assert len(findings) == 2
    assert any("TODO: implement here" in f[1] for f in findings)
    assert any("placeholder" in f[1] for f in findings)


def test_check_swallowed_exceptions() -> None:
    """Test detection of try-except blocks swallowing errors."""
    code = """
try:
    x = 1 / 0
except Exception:
    pass

try:
    x = 1 / 0
except Exception:
    print("error occurred")

try:
    x = 1 / 0
except Exception as e:
    raise ValueError("nested error") from e
"""
    tree = ai_code_sanitizer.ast.parse(code)
    findings = ai_code_sanitizer.check_swallowed_exceptions(tree)

    # We should have exactly 2 swallowed warnings (first try-pass, second try-print)
    assert len(findings) == 2


def test_check_unnecessary_abstractions() -> None:
    """Test single-method classes and trivial delegations."""
    code = """
class UnnecessaryWrapper:
    def __init__(self, val):
        self.val = val

    def perform_action(self):
        return self.val * 2

class UsefulClass:
    def method_one(self):
        pass
    def method_two(self):
        pass

def trivial_delegate(a, b):
    return delegate_target(a, b)

def good_wrapper(a, b):
    # Does something before returning
    res = delegate_target(a, b)
    return res + 1
"""
    tree = ai_code_sanitizer.ast.parse(code)
    findings = ai_code_sanitizer.check_unnecessary_abstractions(tree)

    assert any("UnnecessaryWrapper" in f[1] for f in findings)
    assert any(
        "trivial_delegate" in f[1] and "delegate_target" in f[1] for f in findings
    )
    assert not any("UsefulClass" in f[1] for f in findings)


def test_check_non_verifying_tests() -> None:
    """Test scan of test routines lacking assertions."""
    code = """
def test_one():
    x = 1 + 1

def test_two():
    assert True

def test_three():
    assert 1 == 1

def test_four():
    mock_obj.assert_called_once()
"""
    tree = ai_code_sanitizer.ast.parse(code)
    findings = ai_code_sanitizer.check_non_verifying_tests(tree)

    # test_one has no assert
    assert any("test_one" in f[1] and "zero assert" in f[1] for f in findings)
    # test_two has trivial assert
    assert any("test_two" in f[1] and "static value" in f[1] for f in findings)
    # test_three has trivial compare assert
    assert any("test_three" in f[1] and "static value" in f[1] for f in findings)
    # test_four calls mock assertion and is safe
    assert not any("test_four" in f[1] for f in findings)


def test_cli_success(tmp_path: Path) -> None:
    """Test CLI execution when code is healthy."""
    code = """
def sum_values(a: int, b: int) -> int:
    return a + b
"""
    file_path = tmp_path / "healthy.py"
    file_path.write_text(code, encoding="utf-8")

    args = ["ai_code_sanitizer.py", str(file_path)]
    with patch("sys.argv", args):
        with pytest.raises(SystemExit) as exc:
            ai_code_sanitizer.main()
        assert exc.value.code == 0


def test_cli_failure(tmp_path: Path) -> None:
    """Test CLI execution when issues are found."""
    code = """
import non_existent_pkg
"""
    file_path = tmp_path / "bad.py"
    file_path.write_text(code, encoding="utf-8")

    args = ["ai_code_sanitizer.py", str(file_path)]
    with patch("sys.argv", args):
        with pytest.raises(SystemExit) as exc:
            ai_code_sanitizer.main()
        assert exc.value.code == 1


def test_cli_missing_file() -> None:
    """Test CLI handles missing file path."""
    args = ["ai_code_sanitizer.py", "non_existent_file.py"]
    with patch("sys.argv", args):
        with pytest.raises(SystemExit) as exc:
            ai_code_sanitizer.main()
        assert exc.value.code == 1


def test_cli_parse_error(tmp_path: Path) -> None:
    """Test CLI handles syntax error in scanned file."""
    bad_code = "def bad_syntax("
    file_path = tmp_path / "broken.py"
    file_path.write_text(bad_code, encoding="utf-8")

    args = ["ai_code_sanitizer.py", str(file_path)]
    with patch("sys.argv", args):
        with pytest.raises(SystemExit) as exc:
            ai_code_sanitizer.main()
        assert exc.value.code == 1
