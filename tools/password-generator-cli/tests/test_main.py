"""
Unit tests for Password Generator CLI.
"""

import io
import string
import unittest
from contextlib import redirect_stdout
from typing import List

from main import (
    DEFAULT_WORDLIST,
    build_parser,
    calculate_entropy,
    generate_passphrase,
    generate_password,
    main,
    rate_entropy,
)


class TestPasswordGenerator(unittest.TestCase):

    def test_calculate_entropy_and_rating(self):
        entropy = calculate_entropy(pool_size=94, length=16)
        self.assertAlmostEqual(entropy, 104.88, places=1)
        self.assertIn("Strong", rate_entropy(entropy))

        weak_entropy = calculate_entropy(pool_size=10, length=4)
        self.assertIn("Weak", rate_entropy(weak_entropy))

    def test_generate_password_length_and_sets(self):
        pwd, entropy, rating = generate_password(
            length=20, use_upper=True, use_lower=True, use_digits=True, use_symbols=True
        )
        self.assertEqual(len(pwd), 20)
        self.assertTrue(any(c in string.ascii_uppercase for c in pwd))
        self.assertTrue(any(c in string.ascii_lowercase for c in pwd))
        self.assertTrue(any(c in string.digits for c in pwd))
        self.assertTrue(any(c in string.punctuation for c in pwd))
        self.assertGreater(entropy, 80)

    def test_generate_password_exclusions(self):
        pwd, _, _ = generate_password(length=30, exclude="abc123XYZ")
        for char in "abc123XYZ":
            self.assertNotIn(char, pwd)

    def test_generate_passphrase(self):
        phrase, entropy, rating = generate_passphrase(
            word_count=4, separator="-", capitalize=True, include_number=True
        )
        parts = phrase.split("-")
        self.assertEqual(len(parts), 5)  # 4 words + 1 number
        self.assertGreater(entropy, 30)


class TestEntropyAndRatingBoundaries(unittest.TestCase):
    """Test suite for entropy math and rating classification thresholds."""

    def test_non_positive_inputs_yield_zero_entropy(self) -> None:
        self.assertEqual(calculate_entropy(pool_size=0, length=10), 0.0)
        self.assertEqual(calculate_entropy(pool_size=94, length=0), 0.0)

    def test_rating_thresholds(self) -> None:
        self.assertIn("Very Weak", rate_entropy(10.0))
        self.assertIn("Weak", rate_entropy(50.0))
        self.assertIn("Moderate", rate_entropy(70.0))
        self.assertIn("Strong", rate_entropy(100.0))
        self.assertIn("Very Strong", rate_entropy(130.0))


class TestPasswordGenerationRules(unittest.TestCase):
    """Test suite for password generation constraints and failures."""

    def test_all_sets_disabled_raises_value_error(self) -> None:
        with self.assertRaises(ValueError):
            generate_password(
                use_upper=False, use_lower=False, use_digits=False, use_symbols=False
            )

    def test_exclusion_cannot_empties_every_set(self) -> None:
        with self.assertRaises(ValueError):
            generate_password(
                exclude=string.ascii_letters + string.digits + string.punctuation
            )

    def test_minimum_length_respects_selected_sets(self) -> None:
        """Length is raised so every chosen set can contribute a character."""
        pwd, _, _ = generate_password(
            length=2,
            use_upper=True,
            use_lower=True,
            use_digits=True,
            use_symbols=True,
        )
        self.assertEqual(len(pwd), 4)

    def test_empty_wordlist_rejected(self) -> None:
        with self.assertRaises(ValueError):
            generate_passphrase(wordlist=[])

    def test_passphrase_plain_mode(self) -> None:
        phrase, _, _ = generate_passphrase(
            word_count=3,
            separator=".",
            capitalize=False,
            include_number=False,
            wordlist=["alpha", "beta"],
        )
        parts: List[str] = phrase.split(".")
        self.assertEqual(parts, [p for p in parts])  # structure sanity
        for part in parts:
            self.assertTrue(part in ("alpha", "beta"))


class TestPasswordCli(unittest.TestCase):
    """End-to-end tests for build_parser and the main() entry point."""

    def test_build_parser_password_defaults_and_flags(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["password", "-l", "24", "--no-symbols"])
        self.assertEqual(args.mode, "password")
        self.assertEqual(args.length, 24)
        self.assertTrue(args.no_symbols)
        self.assertEqual(args.exclude, "")

    def test_build_parser_passphrase_flags(self) -> None:
        parser = build_parser()
        args = parser.parse_args(
            ["passphrase", "-w", "6", "-s", "_", "--no-capitalize", "--no-number"]
        )
        self.assertEqual(args.words, 6)
        self.assertEqual(args.separator, "_")
        self.assertTrue(args.no_capitalize)
        self.assertTrue(args.no_number)

    def _capture_main(self, args: List[str]) -> str:
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = main(args)
        self.assertEqual(rc, 0)
        return buf.getvalue()

    def test_main_default_is_password_mode(self) -> None:
        out = self._capture_main([])
        self.assertIn("Password:", out)
        self.assertIn("Entropy:", out)

    def test_main_password_with_exclusions_and_disabled_sets(self) -> None:
        out = self._capture_main(
            ["password", "--no-digits", "--no-symbols", "-e", "lI1O0"]
        )
        pwd_line = next(line for line in out.splitlines() if "Password:" in line)
        pwd = pwd_line.split("Password:")[1].strip()
        for banned in "lI1O0":
            self.assertNotIn(banned, pwd)
        self.assertFalse(any(c.isdigit() for c in pwd))

    def test_main_passphrase_mode(self) -> None:
        out = self._capture_main(["passphrase", "--no-capitalize", "--no-number"])
        self.assertIn("Passphrase:", out)
        phrase_line = next(line for line in out.splitlines() if "Passphrase:" in line)
        phrase = phrase_line.split("Passphrase:")[1].strip()
        words = phrase.split("-")
        self.assertEqual(len(words), 4)
        self.assertTrue(all(w in DEFAULT_WORDLIST for w in words))


if __name__ == "__main__":
    unittest.main()
