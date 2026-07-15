# pylint: skip-file
# mypy: ignore-errors
import unittest.mock

# Whitelist mock attributes used in test_commit_splitter.py
unittest.mock.MagicMock.return_value
unittest.mock.MagicMock.side_effect
