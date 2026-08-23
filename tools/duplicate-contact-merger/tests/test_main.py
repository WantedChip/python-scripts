import contextlib
import csv
import io
import json
import tempfile
import unittest
from pathlib import Path
from typing import Any, Dict, List

from main import (
    are_contacts_duplicate,
    build_parser,
    calculate_name_similarity,
    cluster_duplicate_contacts,
    main,
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


class TestKeyNormalizationEdgeCases(unittest.TestCase):
    """Degenerate inputs to the exact-match key normalizers."""

    def test_empty_email_normalizes_to_empty_string(self) -> None:
        self.assertEqual(normalize_email_key(""), "")
        self.assertEqual(normalize_email_key("   "), "")

    def test_short_or_missing_phone_yields_empty_key(self) -> None:
        self.assertEqual(normalize_phone_key(""), "")
        self.assertEqual(normalize_phone_key("123"), "")
        self.assertEqual(normalize_phone_key("(415) 555"), "")

    def test_name_similarity_with_blank_inputs_is_zero(self) -> None:
        self.assertEqual(calculate_name_similarity("", "Someone"), 0.0)
        self.assertEqual(calculate_name_similarity("Someone", "  "), 0.0)


class TestDuplicateDetectionRules(unittest.TestCase):
    """Field-by-field duplicate rules in ``are_contacts_duplicate``."""

    def setUp(self) -> None:
        self.base: Dict[str, str] = {"name": "", "email": "", "phone": ""}

    def _rec(self, **overrides: str) -> Dict[str, str]:
        record = dict(self.base)
        record.update(overrides)
        return record

    def test_exact_email_match_wins_despite_different_names(self) -> None:
        a = self._rec(name="Ann A", email="shared@x.com")
        b = self._rec(name="Bob B", email="SHARED@x.com")
        self.assertTrue(are_contacts_duplicate(a, b, "name", "email", "phone"))

    def test_phone_formatting_differences_still_match(self) -> None:
        a = self._rec(phone="(415) 555-0000")
        b = self._rec(phone="415.555.0000")
        self.assertTrue(are_contacts_duplicate(a, b, "name", "email", "phone"))

    def test_fuzzy_name_match_above_threshold(self) -> None:
        a = self._rec(name="Katherine Liz Hepburn")
        b = self._rec(name="Katherine Hepburn")
        self.assertTrue(are_contacts_duplicate(a, b, "name", "email", "phone"))

    def test_distinct_contacts_are_not_duplicates(self) -> None:
        a = self._rec(name="Zed Zane", email="z@x.com", phone="1111111111")
        b = self._rec(name="Amy Cole", email="a@x.com", phone="2222222222")
        self.assertFalse(are_contacts_duplicate(a, b, "name", "email", "phone"))

    def test_records_without_any_comparable_fields_are_never_duplicates(
        self,
    ) -> None:
        a = self._rec()
        b = self._rec()
        self.assertFalse(are_contacts_duplicate(a, b, "name", "email", "phone"))


class TestClusteringBehaviour(unittest.TestCase):
    """Union-find clustering including transitive duplicates."""

    @staticmethod
    def _contact(name: str, email: str = "", phone: str = "") -> Dict[str, str]:
        return {"name": name, "email": email, "phone": phone}

    def test_transitive_links_form_one_cluster(self) -> None:
        records = [
            self._contact("A One", email="link@x.com"),
            self._contact("B Two", email="link@x.com", phone="4155551234"),
            self._contact("C Three", phone="4155551234"),
        ]
        clusters = cluster_duplicate_contacts(records, "name", "email", "phone")
        self.assertEqual(len(clusters), 1)
        self.assertEqual(len(clusters[0]), 3)

    def test_unrelated_records_form_separate_singletons(self) -> None:
        records = [
            self._contact("Alpha", email="alpha@x.com"),
            self._contact("Beta", email="beta@x.com"),
        ]
        clusters = cluster_duplicate_contacts(records, "name", "email", "phone")
        self.assertEqual(sorted(len(c) for c in clusters), [1, 1])


class TestMergeStrategies(unittest.TestCase):
    """Conflict resolution strategies of ``merge_cluster``."""

    HEADERS = ["name", "email", "note"]

    def test_single_record_cluster_returns_copy_not_alias(self) -> None:
        original = {"name": "Solo", "email": "", "note": ""}
        merged = merge_cluster([original], self.HEADERS)
        self.assertEqual(merged, original)
        self.assertIsNot(merged, original)

    def test_prefer_non_null_takes_first_available_value(self) -> None:
        cluster = [
            {"name": "First", "email": "", "note": ""},
            {"name": "", "email": "second@x.com", "note": ""},
        ]
        merged = merge_cluster(cluster, self.HEADERS, strategy="prefer_non_null")
        self.assertEqual(merged["name"], "First")
        self.assertEqual(merged["email"], "second@x.com")

    def test_field_empty_everywhere_resolves_to_empty_string(self) -> None:
        cluster = [
            {"name": "X", "email": "", "note": ""},
            {"name": "Y", "email": "", "note": ""},
        ]
        merged = merge_cluster(cluster, self.HEADERS, strategy="prefer_longest")
        self.assertEqual(merged["note"], "")


class TestProcessMergeCsvValidation(unittest.TestCase):
    """Input validation and empty-input handling of process_merge_csv."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.dir_path = Path(self.temp_dir.name)
        self.output = self.dir_path / "merged.csv"

    def test_missing_input_file_raises_file_not_found(self) -> None:
        with self.assertRaises(FileNotFoundError):
            process_merge_csv(self.dir_path / "ghost.csv", self.output)

    def test_headerless_csv_raises_value_error(self) -> None:
        bad = self.dir_path / "bad.csv"
        bad.write_text("", encoding="utf-8")
        with self.assertRaises(ValueError):
            process_merge_csv(bad, self.output)

    def test_header_only_input_produces_header_only_output(self) -> None:
        header_only = self.dir_path / "none.csv"
        header_only.write_text("name,email\n", encoding="utf-8")
        orig, merged = process_merge_csv(header_only, self.output)
        self.assertEqual((orig, merged), (0, 0))
        content = list(csv.reader(self.output.open(encoding="utf-8")))
        self.assertEqual(content, [["name", "email"]])


def _run_cli(args: List[str]) -> Any:
    """Runs ``main`` capturing stdout/stderr; returns (code, out, err)."""
    out_buf, err_buf = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out_buf), contextlib.redirect_stderr(err_buf):
        exit_code = main(args)
    return exit_code, out_buf.getvalue(), err_buf.getvalue()


def _seed_contacts(path: Path) -> None:
    """Writes a small contacts CSV containing one duplicate pair by email."""
    path.write_text(
        "name,email,phone\n"
        "Dana Dane,dana@x.com,4155550001\n"
        "Danny Dane,dana@x.com,\n"
        "Mona Lisa,mona@x.com,4155550002\n",
        encoding="utf-8",
    )


class TestCliEntrypoint(unittest.TestCase):
    """End-to-end CLI runs against temporary CSV files."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.dir_path = Path(self.temp_dir.name)
        self.input_csv = self.dir_path / "contacts.csv"
        self.output_csv = self.dir_path / "out.csv"
        _seed_contacts(self.input_csv)

    def test_successful_merge_reports_counts_and_audit_log(self) -> None:
        log_file = self.dir_path / "audit.json"
        code, out, _ = _run_cli(
            [
                "-i",
                str(self.input_csv),
                "-o",
                str(self.output_csv),
                "--email-col",
                "email",
                "--log-file",
                str(log_file),
            ]
        )
        self.assertEqual(code, 0)
        self.assertIn("Duplicate contact merger complete.", out)
        self.assertIn("Original records: 3", out)
        self.assertIn("Duplicates removed: 1", out)
        self.assertIn(f"Merge audit log saved to: {log_file}", out)

        audit = json.loads(log_file.read_text(encoding="utf-8"))
        self.assertEqual(audit["original_count"], 3)
        self.assertEqual(audit["duplicates_removed"], 1)
        self.assertEqual(len(audit["merged_clusters"]), 1)

        with open(self.output_csv, newline="", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
        self.assertEqual(len(rows), 2)
        dana = next(r for r in rows if "dana" in r["email"])
        self.assertEqual(dana["phone"], "4155550001")

    def test_missing_input_exits_one_with_error_message(self) -> None:
        code, _, err = _run_cli(
            ["-i", str(self.dir_path / "ghost.csv"), "-o", str(self.output_csv)]
        )
        self.assertEqual(code, 1)
        self.assertIn("Error:", err)

    def test_parser_requires_input_and_output(self) -> None:
        with self.assertRaises(SystemExit):
            build_parser().parse_args(["-i", "only_input.csv"])


if __name__ == "__main__":
    unittest.main()
