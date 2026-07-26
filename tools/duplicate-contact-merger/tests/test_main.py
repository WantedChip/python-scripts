import tempfile
import unittest
from pathlib import Path

from main import (
    are_contacts_duplicate,
    calculate_name_similarity,
    merge_cluster,
    normalize_email_key,
    normalize_phone_key,
    process_merge_csv,
)


class TestDuplicateContactMerger(unittest.TestCase):
    """Test suite for duplicate contact merger."""

    def test_calculate_name_similarity(self) -> None:
        self.assertGreater(calculate_name_similarity("John Smith", "John Smith"), 0.99)
        self.assertGreater(
            calculate_name_similarity("John Smith", "John A. Smith"), 0.8
        )
        self.assertLess(calculate_name_similarity("John Smith", "Alice Cooper"), 0.5)

    def test_normalize_keys(self) -> None:
        self.assertEqual(normalize_email_key(" User@Example.COM "), "user@example.com")
        self.assertEqual(normalize_phone_key("+1 (415) 555-2671"), "14155552671")

    def test_are_contacts_duplicate(self) -> None:
        c1 = {
            "name": "John Smith",
            "email": "john@example.com",
            "phone": "415-555-2671",
        }
        c2 = {
            "name": "John Smith",
            "email": "different@example.com",
            "phone": "415-555-2671",
        }
        self.assertTrue(are_contacts_duplicate(c1, c2, "name", "email", "phone"))

    def test_merge_cluster(self) -> None:
        cluster = [
            {"name": "John", "email": "john@example.com", "phone": ""},
            {"name": "John Smith", "email": "", "phone": "4155552671"},
        ]
        merged = merge_cluster(
            cluster, ["name", "email", "phone"], strategy="prefer_longest"
        )
        self.assertEqual(merged["name"], "John Smith")
        self.assertEqual(merged["email"], "john@example.com")
        self.assertEqual(merged["phone"], "4155552671")

    def test_process_merge_csv(self) -> None:
        csv_content = (
            "name,email,phone\n"
            "John Smith,john@example.com,4155552671\n"
            "John A. Smith,john@example.com,\n"
            "Alice,alice@example.com,4155559999\n"
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            input_path = Path(tmpdir) / "input.csv"
            output_path = Path(tmpdir) / "output.csv"
            log_path = Path(tmpdir) / "log.json"
            input_path.write_text(csv_content, encoding="utf-8")

            orig, merged = process_merge_csv(
                input_file=input_path,
                output_file=output_path,
                name_col="name",
                email_col="email",
                phone_col="phone",
                threshold=0.8,
                log_file=log_path,
            )

            self.assertEqual(orig, 3)
            self.assertEqual(merged, 2)
            self.assertTrue(output_path.exists())
            self.assertTrue(log_path.exists())


if __name__ == "__main__":
    unittest.main()
