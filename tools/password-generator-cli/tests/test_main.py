"""
Unit tests for Password Generator CLI.
"""

import string
import unittest

from main import calculate_entropy, generate_passphrase, generate_password, rate_entropy


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


if __name__ == "__main__":
    unittest.main()
