"""
Unit tests for Dictionary Lookup CLI
"""

import contextlib
import io
import json
import unittest
import urllib.error
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock, patch

from main import OFFLINE_LEXICON, DictionaryClient, build_parser, format_display, main


def _configure_urlopen(
    mock_urlopen: MagicMock,
    status: int = 200,
    payload: bytes = b'[{"word": "test", "meanings": []}]',
    error: Optional[Exception] = None,
) -> None:
    """Configures a patched ``urllib.request.urlopen`` with canned behaviour."""
    if error is not None:
        mock_urlopen.side_effect = error
        return
    response = MagicMock()
    response.status = status
    response.read.return_value = payload
    mock_urlopen.return_value.__enter__.return_value = response


def _run_main(args: List[str]) -> Any:
    """Runs ``main`` with redirected stdout; returns (exit_code, output)."""
    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        exit_code = main(args)
    return exit_code, buffer.getvalue()


class TestDictionaryClient(unittest.TestCase):
    """Tests for offline/online lookup behaviour of DictionaryClient."""

    def test_offline_lookup(self) -> None:
        client = DictionaryClient(offline_only=True)
        entries, source = client.lookup("python")
        self.assertEqual(source, "offline")
        self.assertIsNotNone(entries)
        self.assertEqual(entries[0]["word"], "python")

    def test_offline_missing_word(self) -> None:
        client = DictionaryClient(offline_only=True)
        entries, source = client.lookup("nonexistentword12345")
        self.assertEqual(source, "none")
        self.assertIsNone(entries)

    def test_offline_lookup_is_case_insensitive_and_strips(self) -> None:
        client = DictionaryClient(offline_only=True)
        entries, source = client.lookup("  ALGORITHM \n")
        self.assertEqual(source, "offline")
        self.assertEqual(entries[0]["word"], "algorithm")

    @patch("urllib.request.urlopen")
    def test_online_lookup_ok(self, mock_urlopen: MagicMock) -> None:
        _configure_urlopen(mock_urlopen)
        client = DictionaryClient(offline_only=False)
        entries, source = client.lookup("test")
        self.assertEqual(source, "online")
        self.assertEqual(entries[0]["word"], "test")

    @patch("urllib.request.urlopen")
    def test_online_non_200_status_returns_none(self, mock_urlopen: MagicMock) -> None:
        _configure_urlopen(mock_urlopen, status=503)
        client = DictionaryClient(offline_only=False)
        entries, source = client.lookup("anything")
        self.assertIsNone(entries)
        self.assertEqual(source, "none")

    @patch("urllib.request.urlopen")
    def test_online_url_error_returns_none(self, mock_urlopen: MagicMock) -> None:
        _configure_urlopen(mock_urlopen, error=urllib.error.URLError("x"))
        client = DictionaryClient(offline_only=False)
        entries, source = client.lookup("anything")
        self.assertIsNone(entries)
        self.assertEqual(source, "none")

    @patch("urllib.request.urlopen")
    def test_online_non_list_json_returns_none(self, mock_urlopen: MagicMock) -> None:
        _configure_urlopen(mock_urlopen, payload=b'{"oops": true}')
        client = DictionaryClient(offline_only=False)
        entries, source = client.lookup("anything")
        self.assertIsNone(entries)
        self.assertEqual(source, "none")

    @patch("urllib.request.urlopen")
    def test_online_invalid_json_returns_none(self, mock_urlopen: MagicMock) -> None:
        _configure_urlopen(mock_urlopen, payload=b"not json at all")
        client = DictionaryClient(offline_only=False)
        entries, source = client.lookup("anything")
        self.assertIsNone(entries)
        self.assertEqual(source, "none")

    def test_lookup_prefers_online_over_offline(self) -> None:
        client = DictionaryClient(offline_only=False)
        with patch.object(
            client,
            "fetch_online",
            return_value=[{"word": "fast", "meanings": []}],
        ):
            entries, source = client.lookup("fast")
        self.assertEqual(source, "online")
        self.assertEqual(entries[0]["word"], "fast")


class TestFormatDisplay(unittest.TestCase):
    """Tests for human-readable rendering of dictionary entries."""

    def test_full_entry_rendering(self) -> None:
        entries: List[Dict[str, Any]] = [
            {
                "word": "fast",
                "phonetic": "/fæst/",
                "meanings": [
                    {
                        "partOfSpeech": "adjective",
                        "definitions": [
                            {
                                "definition": "Moving at high speed.",
                                "example": "A fast car.",
                            },
                            {"definition": "Firmly fixed.", "example": ""},
                        ],
                        "synonyms": ["quick", "rapid"],
                        "antonyms": ["slow"],
                    }
                ],
            }
        ]
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            format_display("fast", entries, "offline")
        out = buffer.getvalue()
        self.assertIn("WORD DEFINITION: FAST (Source: OFFLINE)", out)
        self.assertIn("Pronunciation: /fæst/", out)
        self.assertIn("Part of Speech: ADJECTIVE", out)
        self.assertIn("1. Moving at high speed.", out)
        self.assertIn('Example: "A fast car."', out)
        self.assertIn("2. Firmly fixed.", out)
        self.assertIn("Synonyms: quick, rapid", out)
        self.assertIn("Antonyms: slow", out)

    def test_phonetics_list_fallback_and_defaults(self) -> None:
        entries: List[Dict[str, Any]] = [
            {
                "phonetics": [{}, {"text": "/ˈpaɪθɑːn/"}],
                "meanings": [
                    {
                        "definitions": [{"definition": "A language."}],
                        "synonyms": [],
                        "antonyms": [],
                    }
                ],
            }
        ]
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            format_display("python", entries, "online")
        out = buffer.getvalue()
        self.assertIn("Pronunciation: /ˈpaɪθɑːn/", out)
        self.assertIn("Part of Speech: GENERAL", out)
        self.assertIn("1. A language.", out)
        self.assertNotIn("Synonyms:", out)
        self.assertNotIn("Antonyms:", out)


class TestMainCli(unittest.TestCase):
    """End-to-end CLI tests exercising every documented flag."""

    def test_word_not_found_returns_exit_code_one(self) -> None:
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            exit_code = main(["lookup", "zzzznotaword", "--offline-only"])
        self.assertEqual(exit_code, 1)
        self.assertIn("not found in online API", buffer.getvalue())

    def test_json_output_includes_source_and_data(self) -> None:
        with patch("urllib.request.urlopen") as mock_urlopen:
            _configure_urlopen(
                mock_urlopen, payload=b'[{"word": "cli", "meanings": []}]'
            )
            exit_code, out = _run_main(["lookup", "cli", "--json"])
        self.assertEqual(exit_code, 0)
        parsed = json.loads(out)
        self.assertEqual(parsed["source"], "online")
        self.assertEqual(parsed["data"][0]["word"], "cli")

    def test_synonyms_flag_prints_sorted_synonyms(self) -> None:
        exit_code, out = _run_main(["lookup", "fast", "--offline-only", "--synonyms"])
        self.assertEqual(exit_code, 0)
        self.assertIn("Synonyms for 'fast': quick, rapid, speedy, swift", out)

    def test_antonyms_flag_prints_sorted_antonyms(self) -> None:
        exit_code, out = _run_main(["lookup", "fast", "--offline-only", "--antonyms"])
        self.assertEqual(exit_code, 0)
        self.assertIn("Antonyms for 'fast': slow, sluggish, tardy", out)

    def test_antonyms_flag_without_matches_prints_none_found(self) -> None:
        exit_code, out = _run_main(["lookup", "python", "--offline-only", "--antonyms"])
        self.assertEqual(exit_code, 0)
        self.assertIn("Antonyms for 'python': None found.", out)

    def test_default_display_for_known_word(self) -> None:
        exit_code, out = _run_main(["lookup", "code", "--offline-only"])
        self.assertEqual(exit_code, 0)
        self.assertIn("WORD DEFINITION: CODE", out)
        self.assertIn("Synonyms: cipher, script, program, encoding", out)

    def test_no_command_prints_help(self) -> None:
        exit_code, out = _run_main([])
        self.assertEqual(exit_code, 0)
        self.assertIn("usage:", out)

    def test_parser_builds_expected_flags(self) -> None:
        parser = build_parser()
        parsed = parser.parse_args(["lookup", "word", "--offline-only"])
        self.assertEqual(parsed.command, "lookup")
        self.assertTrue(parsed.offline_only)
        self.assertFalse(parsed.synonyms)
        self.assertFalse(parsed.antonyms)


class TestOfflineLexiconIntegrity(unittest.TestCase):
    """Sanity checks on the shipped offline lexicon data."""

    def test_lexicon_entries_have_required_shape(self) -> None:
        for word, entries in OFFLINE_LEXICON.items():
            entry = entries[0]
            self.assertEqual(entry["word"], word)
            self.assertIsInstance(entry["phonetic"], str)
            meaning = entry["meanings"][0]
            self.assertTrue(meaning["definitions"])


if __name__ == "__main__":
    unittest.main()
