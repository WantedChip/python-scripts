import json
import pathlib
import tempfile
import unittest

from main import DirectoryComparator, main


class TestDirectoryComparator(unittest.TestCase):

    def setUp(self):
        self.temp_dir_a = tempfile.TemporaryDirectory()
        self.temp_dir_b = tempfile.TemporaryDirectory()

        self.dir_a = pathlib.Path(self.temp_dir_a.name)
        self.dir_b = pathlib.Path(self.temp_dir_b.name)

        # File setup:
        # file1.txt: identical in A and B
        (self.dir_a / "file1.txt").write_text("Hello World", encoding="utf-8")
        (self.dir_b / "file1.txt").write_text("Hello World", encoding="utf-8")

        # file2.txt: modified in B
        (self.dir_a / "file2.txt").write_text("Original content", encoding="utf-8")
        (self.dir_b / "file2.txt").write_text("Modified content", encoding="utf-8")

        # file3.txt: present in A only (missing in B)
        (self.dir_a / "file3.txt").write_text("Only in A", encoding="utf-8")

        # file4.txt: present in B only (extra in B)
        (self.dir_b / "file4.txt").write_text("Only in B", encoding="utf-8")

        # Subdirectory file: ignore.tmp
        (self.dir_a / "ignore.tmp").write_text("Temp file A", encoding="utf-8")
        (self.dir_b / "ignore.tmp").write_text("Temp file B", encoding="utf-8")

    def tearDown(self):
        self.temp_dir_a.cleanup()
        self.temp_dir_b.cleanup()

    def test_compare_directories(self):
        comparator = DirectoryComparator(verify_hash=True)
        report = comparator.compare(self.dir_a, self.dir_b)

        self.assertIn("file1.txt", report.identical_files)
        self.assertIn("file3.txt", report.missing_in_b)
        self.assertIn("file4.txt", report.extra_in_b)

        modified_names = [diff.rel_path for diff in report.modified_files]
        self.assertIn("file2.txt", modified_names)

    def test_exclusion_filter(self):
        comparator = DirectoryComparator(excludes=["*.tmp"])
        report = comparator.compare(self.dir_a, self.dir_b)

        all_processed = (
            report.identical_files
            + report.missing_in_b
            + report.extra_in_b
            + [diff.rel_path for diff in report.modified_files]
        )
        self.assertNotIn("ignore.tmp", all_processed)

    def test_main_cli_execution_with_json_output(self):
        json_report_path = self.dir_a / "report.json"
        exit_code = main(
            [
                str(self.dir_a),
                str(self.dir_b),
                "--exclude",
                "*.tmp",
                "--json-output",
                str(json_report_path),
            ]
        )
        self.assertEqual(exit_code, 0)
        self.assertTrue(json_report_path.exists())

        with open(json_report_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            self.assertEqual(data["summary"]["total_missing"], 1)
            self.assertEqual(data["summary"]["total_extra"], 1)


if __name__ == "__main__":
    unittest.main()
