import ast
import io
import os
import sys
import unittest
from unittest.mock import patch

# Ensure dead_code_confidence is importable
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
import dead_code_confidence  # noqa: E402


# Simple in-memory mock file
class MockFile:
    def __init__(self, content: str):
        self.stream = io.StringIO(content)

    def read(self, size=-1):
        return self.stream.read(size)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        pass

    def __iter__(self):
        return iter(self.stream)

    def __next__(self):
        return next(self.stream)


class TestDeadCodeConfidence(unittest.TestCase):

    def setUp(self):
        self.content_dict = {}

        def open_side_effect(file_path, mode="r", *args, **kwargs):
            norm_path = os.path.abspath(file_path)
            if norm_path not in self.content_dict:
                for k, v in self.content_dict.items():
                    if norm_path.endswith(k) or k.endswith(norm_path):
                        return MockFile(v)
                raise FileNotFoundError(f"No mock content for {file_path}")
            return MockFile(self.content_dict[norm_path])

        self.open_patcher = patch("builtins.open", side_effect=open_side_effect)
        self.open_patcher.start()

    def tearDown(self):
        self.open_patcher.stop()

    def test_symbol_visitor(self):
        code = """
class MyClass:
    def my_method(self):
        pass
    def __init__(self):
        pass

def my_func():
    pass
"""
        tree = ast.parse(code)
        visitor = dead_code_confidence.SymbolVisitor("dummy_file.py")
        visitor.visit(tree)

        symbols = visitor.symbols
        names = [s["name"] for s in symbols]
        types = [s["type"] for s in symbols]

        self.assertIn("MyClass", names)
        self.assertIn("my_method", names)
        self.assertIn("my_func", names)
        self.assertNotIn("__init__", names)
        self.assertEqual(types[names.index("MyClass")], "Class")
        self.assertEqual(types[names.index("my_method")], "Function/Method")
        self.assertEqual(types[names.index("my_func")], "Function/Method")

    @patch("os.walk")
    def test_gather_declarations(self, mock_walk):
        mock_walk.return_value = [
            ("/mock/dir", [".git", "src"], ["app.py"]),
            ("/mock/dir/.git", [], ["config"]),
            ("/mock/dir/src", [], ["utils.py"]),
        ]

        app_py_path = os.path.abspath("/mock/dir/app.py")
        self.content_dict[app_py_path] = "def main_func(): pass"

        decls = dead_code_confidence.gather_declarations("/mock/dir")
        names = [d["name"] for d in decls]
        self.assertEqual(names, ["main_func"])

    @patch("os.walk")
    def test_gather_declarations_syntax_error(self, mock_walk):
        mock_walk.return_value = [("/mock/dir", [], ["invalid.py"])]
        invalid_py_path = os.path.abspath("/mock/dir/invalid.py")
        self.content_dict[invalid_py_path] = "this is a syntax error!"

        decls = dead_code_confidence.gather_declarations("/mock/dir")
        self.assertEqual(decls, [])

    def test_calculate_confidence_never_referenced(self):
        decl = {"name": "unused_func", "file": "/mock/dir/app.py", "line": 5}
        occurrences = {}
        conf, reasons = dead_code_confidence.calculate_confidence(decl, occurrences)
        self.assertEqual(conf, 99)
        self.assertTrue(any("never referenced anywhere" in r for r in reasons))

    def test_calculate_confidence_only_tests(self):
        decl = {"name": "unused_func", "file": "/mock/dir/app.py", "line": 5}
        occurrences = {
            "unused_func": [
                ("/mock/dir/app.py", 5),
                ("/mock/dir/tests/test_app.py", 10),
            ]
        }
        conf, reasons = dead_code_confidence.calculate_confidence(decl, occurrences)
        self.assertEqual(conf, 90)
        self.assertTrue(any("only referenced in test files" in r for r in reasons))

    def test_calculate_confidence_referenced_in_production(self):
        decl = {"name": "unused_func", "file": "/mock/dir/app.py", "line": 5}
        occurrences = {
            "unused_func": [
                ("/mock/dir/app.py", 5),
                ("/mock/dir/main.py", 20),
            ]
        }
        conf, reasons = dead_code_confidence.calculate_confidence(decl, occurrences)
        self.assertEqual(conf, 0)
        self.assertEqual(reasons, [])

    @patch("sys.argv", ["dead_code_confidence.py", "/mock/invalid_path"])
    @patch("os.path.exists")
    @patch("sys.exit")
    def test_main_path_not_exists(self, mock_exit, mock_exists):
        mock_exists.return_value = False
        mock_exit.side_effect = SystemExit(1)

        with self.assertRaises(SystemExit) as cm:
            dead_code_confidence.main()
        self.assertEqual(cm.exception.code, 1)

    @patch("sys.argv", ["dead_code_confidence.py", "/mock/dir"])
    @patch("os.path.exists")
    @patch("dead_code_confidence.gather_declarations")
    @patch("sys.exit")
    def test_main_no_declarations(self, mock_exit, mock_gather, mock_exists):
        mock_exists.return_value = True
        mock_gather.return_value = []
        mock_exit.side_effect = SystemExit(0)

        with self.assertRaises(SystemExit) as cm:
            dead_code_confidence.main()
        self.assertEqual(cm.exception.code, 0)

    @patch("sys.argv", ["dead_code_confidence.py", "/mock/dir"])
    @patch("os.path.exists")
    @patch("dead_code_confidence.gather_declarations")
    @patch("os.walk")
    @patch("sys.exit")
    def test_main_with_candidates(self, mock_exit, mock_walk, mock_gather, mock_exists):
        mock_exists.return_value = True

        app_path = os.path.abspath("/mock/dir/app.py")

        mock_gather.return_value = [
            {
                "name": "unused_func",
                "type": "Function/Method",
                "line": 1,
                "file": app_path,
            }
        ]

        mock_walk.return_value = [("/mock/dir", [], ["app.py"])]
        self.content_dict[app_path] = "def unused_func(): pass"

        dead_code_confidence.main()
        mock_exit.assert_not_called()


if __name__ == "__main__":
    unittest.main()
