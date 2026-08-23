"""
Unit tests for JSON Formatter CLI
"""

import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from main import (
    COLOR_BOOL,
    COLOR_KEY,
    COLOR_NULL,
    COLOR_NUMBER,
    COLOR_RESET,
    COLOR_STRING,
    JSONFormatter,
    JSONQueryEngine,
    JSONSchemaValidator,
    load_json_source,
    main,
)


class TestJSONFormatter(unittest.TestCase):
    def test_minify(self) -> None:
        data = {"name": "Alice", "age": 30, "items": [1, 2, 3]}
        minified = JSONFormatter.minify(data)
        self.assertEqual(minified, '{"name":"Alice","age":30,"items":[1,2,3]}')

    def test_pretty_print_no_color(self) -> None:
        data = {"a": 1}
        output = JSONFormatter.pretty_print(data, colorize=False)
        self.assertIn('"a": 1', output)


class TestJSONQueryEngine(unittest.TestCase):
    def test_parse_path(self) -> None:
        tokens = JSONQueryEngine.parse_path("users[0].name")
        self.assertEqual(tokens, ["users", 0, "name"])

    def test_execute_query_dict_and_array(self) -> None:
        data = {"store": {"books": [{"title": "Book 1"}, {"title": "Book 2"}]}}
        success, val = JSONQueryEngine.execute_query(data, "store.books[1].title")
        self.assertTrue(success)
        self.assertEqual(val, "Book 2")

    def test_execute_query_not_found(self) -> None:
        data = {"a": 1}
        success, err = JSONQueryEngine.execute_query(data, "b")
        self.assertFalse(success)
        self.assertIn("not found", err)


class TestJSONSchemaValidator(unittest.TestCase):
    def test_schema_validation_success(self) -> None:
        data = {"name": "Bob", "age": 25}
        schema = {
            "type": "object",
            "required": ["name", "age"],
            "properties": {"name": {"type": "string"}, "age": {"type": "integer"}},
        }
        valid, errors = JSONSchemaValidator.validate(data, schema)
        self.assertTrue(valid)
        self.assertEqual(len(errors), 0)

    def test_schema_validation_missing_required(self) -> None:
        data = {"name": "Bob"}
        schema = {"type": "object", "required": ["name", "age"]}
        valid, errors = JSONSchemaValidator.validate(data, schema)
        self.assertFalse(valid)
        self.assertIn("Missing required property key 'age'.", errors[0])


class TestJSONQueryEnginePaths(unittest.TestCase):
    """Tests for query path parsing edge cases and navigation errors."""

    def test_parse_path_leading_dot(self) -> None:
        """A leading dot is stripped so '.store.item' resolves like a key path."""
        tokens = JSONQueryEngine.parse_path(".store.item")
        self.assertEqual(tokens, ["store", "item"])

    def test_parse_path_dot_only_returns_empty(self) -> None:
        """A path consisting of only a dot yields no tokens."""
        self.assertEqual(JSONQueryEngine.parse_path("."), [])
        self.assertEqual(JSONQueryEngine.parse_path("   "), [])

    def test_parse_path_skips_empty_segments(self) -> None:
        """Empty segments from doubled dots are ignored during tokenizing."""
        tokens = JSONQueryEngine.parse_path("a..b")
        self.assertEqual(tokens, ["a", "b"])

    def test_execute_query_index_out_of_bounds(self) -> None:
        """An array index past the end reports the failure with array length."""
        data = {"items": [1, 2]}
        success, err = JSONQueryEngine.execute_query(data, "items[5]")
        self.assertFalse(success)
        self.assertIn("out of bounds for array length 2", err)

    def test_execute_query_index_into_non_array(self) -> None:
        """Applying an index to a scalar reports zero-length array bounds."""
        success, err = JSONQueryEngine.execute_query({"a": 1}, "a[0]")
        self.assertFalse(success)
        self.assertIn("Index [0] out of bounds for array length 0", err)


class TestJSONFormatterColorize(unittest.TestCase):
    """Tests for ANSI colorization of pretty-printed JSON."""

    def test_pretty_print_colorized_by_default(self) -> None:
        """Default pretty printing routes through the colorizer."""
        output = JSONFormatter.pretty_print({"a": 1})
        self.assertIn(COLOR_KEY, output)
        self.assertIn(COLOR_NUMBER, output)

    def test_colorize_covers_all_value_kinds(self) -> None:
        """Strings, booleans, nulls, numbers, and containers are all colored."""
        data = {
            "text": "hello",
            "flag": True,
            "off": False,
            "missing": None,
            "count": 42,
            "ratio": 3.14,
            "child": {"inner": 1},
        }
        output = JSONFormatter.colorize_json(json.dumps(data, indent=2))

        # Keys are wrapped in the key color (indent included inside the span).
        self.assertIn(COLOR_KEY, output)
        for key in ("text", "flag", "off", "missing", "count", "ratio", "child"):
            self.assertIn(f'"{key}"', output)
        self.assertIn(f'{COLOR_STRING}"hello"{COLOR_RESET}', output)
        self.assertIn(f"{COLOR_BOOL}true{COLOR_RESET}", output)
        self.assertIn(f"{COLOR_BOOL}false{COLOR_RESET}", output)
        self.assertIn(f"{COLOR_NULL}null{COLOR_RESET}", output)
        self.assertIn(f"{COLOR_NUMBER}42{COLOR_RESET}", output)
        self.assertIn(f"{COLOR_NUMBER}3.14{COLOR_RESET}", output)
        # Nested object braces fall into the non-scalar fallback branch.
        self.assertIn("{", output)

    def test_colorize_lines_without_keys_unchanged(self) -> None:
        """Lines without a quoted key (array items, braces) pass through."""
        raw = "[\n  1,\n  2\n]"
        self.assertEqual(JSONFormatter.colorize_json(raw), raw)


class TestJSONSchemaValidatorTypes(unittest.TestCase):
    """Tests for root type checking and nested property error reporting."""

    def test_root_type_mismatch(self) -> None:
        """Data whose root type differs from the schema fails immediately."""
        valid, errors = JSONSchemaValidator.validate(
            "not-an-object", {"type": "object"}
        )
        self.assertFalse(valid)
        self.assertTrue(errors[0].startswith("Root data type mismatch"))

    def test_nested_property_errors_are_prefixed(self) -> None:
        """Errors from property schemas carry the property name prefix."""
        data = {"age": "old"}
        schema = {"properties": {"age": {"type": "number"}}}
        valid, errors = JSONSchemaValidator.validate(data, schema)
        self.assertFalse(valid)
        self.assertEqual(len(errors), 1)
        self.assertTrue(errors[0].startswith("Property 'age':"))


class TestLoadJsonSource(unittest.TestCase):
    """Tests for loading JSON from inline strings and file paths."""

    def test_inline_object_string(self) -> None:
        """Raw JSON text starting with '{' is parsed directly."""
        ok, data = load_json_source('{"a": 1}')
        self.assertTrue(ok)
        self.assertEqual(data, {"a": 1})

    def test_inline_array_string(self) -> None:
        """Raw JSON text starting with '[' is parsed directly."""
        ok, data = load_json_source("[1, 2]")
        self.assertTrue(ok)
        self.assertEqual(data, [1, 2])

    def test_file_source(self) -> None:
        """JSON is read from a file path that does not look inline."""
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "data.json"
            path.write_text('{"k": [true, null]}', encoding="utf-8")
            ok, data = load_json_source(str(path))
        self.assertTrue(ok)
        self.assertEqual(data, {"k": [True, None]})

    def test_invalid_inline_json_fails(self) -> None:
        """Malformed inline JSON reports failure with an error message."""
        ok, err = load_json_source("{not json}")
        self.assertFalse(ok)
        self.assertIn("Failed to parse JSON", err)

    def test_missing_file_fails(self) -> None:
        """A nonexistent file path reports failure instead of raising."""
        ok, err = load_json_source("Z:/definitely/missing/file.json")
        self.assertFalse(ok)
        self.assertIn("Failed to parse JSON", err)


class TestMainCLI(unittest.TestCase):
    """End-to-end CLI tests for every subcommand and error branch."""

    def test_format_inline_with_color(self) -> None:
        """Format command pretty-prints inline JSON and exits 0."""
        buf = io.StringIO()
        with redirect_stdout(buf):
            code = main(["format", '{"a": 1}'])
        self.assertEqual(code, 0)
        self.assertIn(COLOR_KEY, buf.getvalue())
        self.assertIn('"a"', buf.getvalue())

    def test_format_file_no_color(self) -> None:
        """Format command reads files and honors --no-color."""

        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "in.json"
            src.write_text('{"b": true}', encoding="utf-8")
            buf = io.StringIO()
            with redirect_stdout(buf):
                code = main(["format", str(src), "--no-color"])
        self.assertEqual(code, 0)
        self.assertIn('"b": true', buf.getvalue())

    def test_format_bad_source_returns_error(self) -> None:
        """Format command exits 1 when the source cannot be parsed."""
        code = main(["format", "{oops"])
        self.assertEqual(code, 1)

    def test_minify_command(self) -> None:
        """Minify command prints compact JSON for both strings and files."""

        buf = io.StringIO()
        with redirect_stdout(buf):
            code = main(["minify", '{"x" : [ 1 , 2 ]}'])
        self.assertEqual(code, 0)
        self.assertIn('{"x":[1,2]}', buf.getvalue())

    def test_minify_bad_source_returns_error(self) -> None:
        """Minify command exits 1 when the source cannot be parsed."""
        self.assertEqual(main(["minify", "nope"]), 1)

    def test_query_scalar_result(self) -> None:
        """Query command prints scalar results verbatim and exits 0."""

        buf = io.StringIO()
        with redirect_stdout(buf):
            code = main(["query", '{"user": {"name": "Ann"}}', "user.name"])
        self.assertEqual(code, 0)
        self.assertIn("Ann", buf.getvalue())

    def test_query_container_no_color(self) -> None:
        """Container query results are pretty printed honoring --no-color."""

        buf = io.StringIO()
        with redirect_stdout(buf):
            code = main(["query", '{"u": [{"n": 1}]}', "u", "--no-color"])
        self.assertEqual(code, 0)
        self.assertIn('"n": 1', buf.getvalue())
        self.assertNotIn("\033[", buf.getvalue())

    def test_query_miss_returns_error(self) -> None:
        """Query command exits 1 when the path does not resolve."""
        code = main(["query", '{"a": 1}', "missing.key"])
        self.assertEqual(code, 1)

    def test_query_bad_source_returns_error(self) -> None:
        """Query command exits 1 when the source cannot be parsed."""
        self.assertEqual(main(["query", "{{", "a"]), 1)

    def test_validate_success_and_failure(self) -> None:
        """Validate command passes on conforming data and fails otherwise."""
        schema = '{"type": "object", "required": ["id"]}'
        good = io.StringIO()
        with redirect_stdout(good):
            code_ok = main(["validate", '{"id": 7}', schema])
        self.assertEqual(code_ok, 0)
        self.assertIn("Validation PASSED", good.getvalue())

        bad = io.StringIO()
        with redirect_stdout(bad):
            code_bad = main(["validate", '{"other": 7}', schema])
        self.assertEqual(code_bad, 1)
        self.assertIn("Validation FAILED", bad.getvalue())
        self.assertIn("- Missing required property key 'id'.", bad.getvalue())

    def test_validate_data_error_returns_error(self) -> None:
        """Validate command exits 1 when the data source fails to load."""
        self.assertEqual(main(["validate", "{{", "{}"]), 1)

    def test_validate_schema_error_returns_error(self) -> None:
        """Validate command exits 1 when the schema source fails to load."""
        self.assertEqual(main(["validate", "{}", "{{"]), 1)

    def test_no_command_prints_help(self) -> None:
        """Invoking with no subcommand prints help and exits 0."""

        buf = io.StringIO()
        with redirect_stdout(buf):
            code = main([])
        self.assertEqual(code, 0)
        self.assertIn("usage:", buf.getvalue())


if __name__ == "__main__":
    unittest.main()
