"""Unit tests for example_drift_checker.py."""

import ast
import sys
from pathlib import Path
from unittest.mock import mock_open, patch

import pytest

# Add import injection to resolve checkers package
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# pylint: disable=import-error, wrong-import-position
import example_drift_checker  # noqa: E402


def test_declaration_scanner() -> None:
    """Test AST scanner for declarations of classes and functions."""
    code = """
class TestClass:
    def method_one(self, x, y):
        pass

def test_func(a, b=2, *args, **kwargs):
    pass

def __init__(self):
    pass

def __custom_special__(self):
    pass
"""
    tree = ast.parse(code)
    scanner = example_drift_checker.DeclarationScanner()
    scanner.visit(tree)

    assert "TestClass" in scanner.definitions
    assert scanner.definitions["TestClass"]["type"] == "Class"

    assert "method_one" in scanner.definitions
    assert scanner.definitions["method_one"]["args"] == ["self", "x", "y"]

    assert "test_func" in scanner.definitions
    assert scanner.definitions["test_func"]["args"] == ["a", "b"]

    # Special methods starting and ending with __ should be ignored
    assert "__init__" not in scanner.definitions
    assert "__custom_special__" not in scanner.definitions


def test_example_usage_scanner() -> None:
    """Test AST scanner for example usage calls."""
    code = """
func_call(1, arg2=3)
obj.method_call(val=4)
nested.nested_call(5)
"""
    tree = ast.parse(code)
    scanner = example_drift_checker.ExampleUsageScanner()
    scanner.visit(tree)

    assert len(scanner.calls) == 3

    # Check func_call
    c1 = next(c for c in scanner.calls if c["name"] == "func_call")
    assert c1["num_args"] == 1
    assert c1["keywords"] == ["arg2"]

    # Check method_call
    c2 = next(c for c in scanner.calls if c["name"] == "method_call")
    assert c2["num_args"] == 0
    assert c2["keywords"] == ["val"]

    # Check nested_call
    c3 = next(c for c in scanner.calls if c["name"] == "nested_call")
    assert c3["num_args"] == 1
    assert c3["keywords"] == []


def test_index_source_apis(tmp_path: Path) -> None:
    """Test indexing of APIs in source files, including exclude dirs."""
    src_dir = tmp_path / "src"
    src_dir.mkdir()

    # Valid Python file
    valid_file = src_dir / "valid.py"
    valid_file.write_text("def hello(name):\n    pass\n", encoding="utf-8")

    # Excluded directory file
    excluded_dir = src_dir / "venv"
    excluded_dir.mkdir()
    excluded_file = excluded_dir / "ignored.py"
    excluded_file.write_text("def ignored_func():\n    pass\n", encoding="utf-8")

    # File with syntax error
    broken_file = src_dir / "broken.py"
    broken_file.write_text("def broken_func(\n", encoding="utf-8")

    definitions = example_drift_checker.index_source_apis(str(src_dir))

    # hello should be indexed
    assert "hello" in definitions
    assert definitions["hello"]["args"] == ["name"]

    # ignored_func from excluded dir should NOT be indexed
    assert "ignored_func" not in definitions

    # broken_func from syntax error file should NOT be indexed
    assert "broken_func" not in definitions


def test_extract_python_blocks(tmp_path: Path) -> None:
    """Test extracting python code blocks from markdown documentation."""
    doc_path = tmp_path / "README.md"
    content = """
# Documentation

Here is an example:
```python
x = 10
y = func(x)
```

And another code block:
```py
val = 5
```

Normal text block.
```text
Some other block
```
"""
    doc_path.write_text(content, encoding="utf-8")

    blocks = example_drift_checker.extract_python_blocks(str(doc_path))
    assert len(blocks) == 2

    # Block 1
    assert "x = 10" in blocks[0][0]
    assert blocks[0][1] == 6  # Line starts at 6 (1-indexed)

    # Block 2
    assert "val = 5" in blocks[1][0]
    assert blocks[1][1] == 12  # Line starts at 12


def test_extract_python_blocks_missing_or_error(tmp_path: Path) -> None:
    """Test that non-existent files or OS errors return empty lists."""
    assert example_drift_checker.extract_python_blocks("non_existent_file.md") == []

    # Mock open raising OSError
    with patch("builtins.open", mock_open()) as mock_file:
        mock_file.side_effect = OSError("Permission denied")
        assert example_drift_checker.extract_python_blocks("some_file.md") == []


def test_main_success(tmp_path: Path) -> None:
    """Test CLI runs successfully when there are no drifts."""
    src_dir = tmp_path / "src"
    src_dir.mkdir()
    (src_dir / "app.py").write_text(
        "def compute(value, factor=2):\n    pass\n", encoding="utf-8"
    )

    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    (docs_dir / "guide.md").write_text(
        """
# User Guide
```python
compute(10, factor=5)
```
""",
        encoding="utf-8",
    )

    args = ["example_drift_checker.py", "--src", str(src_dir), "--docs", str(docs_dir)]
    with patch("sys.argv", args):
        with pytest.raises(SystemExit) as exc:
            example_drift_checker.main()
        assert exc.value.code == 0


def test_main_drift_detected(tmp_path: Path) -> None:
    """Test CLI executes and highlights drifts when keyword args do not match."""
    src_dir = tmp_path / "src"
    src_dir.mkdir()
    (src_dir / "app.py").write_text(
        "def compute(value, factor=2):\n    pass\n", encoding="utf-8"
    )

    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    (docs_dir / "guide.md").write_text(
        """
# User Guide
```python
compute(10, non_existent_arg=5)
```
""",
        encoding="utf-8",
    )

    args = ["example_drift_checker.py", "--src", str(src_dir), "--docs", str(docs_dir)]
    with patch("sys.argv", args):
        example_drift_checker.main()
