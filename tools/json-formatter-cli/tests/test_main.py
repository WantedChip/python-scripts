"""
Unit tests for JSON Formatter CLI
"""

import unittest

from main import JSONFormatter, JSONQueryEngine, JSONSchemaValidator


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


if __name__ == "__main__":
    unittest.main()
