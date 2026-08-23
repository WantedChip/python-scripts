"""Unit tests for Outlier Detector CSV tool."""

import contextlib
import csv
import io
import json
import tempfile
import unittest
from pathlib import Path
from typing import List

from main import (
    calculate_percentile,
    detect_outliers_iqr,
    detect_outliers_zscore,
    main,
    parse_args,
    print_report,
    process_csv,
)


class TestOutlierDetector(unittest.TestCase):
    """Test suite for outlier detection functions and CSV processor."""

    def test_calculate_percentile(self) -> None:
        values = [10.0, 20.0, 30.0, 40.0, 50.0]
        self.assertEqual(calculate_percentile(values, 0.0), 10.0)
        self.assertEqual(calculate_percentile(values, 50.0), 30.0)
        self.assertEqual(calculate_percentile(values, 100.0), 50.0)

    def test_detect_outliers_iqr(self) -> None:
        values = [10.0, 12.0, 11.0, 13.0, 12.0, 100.0]
        is_outlier, stats = detect_outliers_iqr(values, threshold=1.5)
        self.assertTrue(is_outlier[-1])
        self.assertFalse(is_outlier[0])
        self.assertIn("iqr", stats)

    def test_detect_outliers_zscore(self) -> None:
        values = [10.0, 10.0, 10.0, 10.0, 10.0, 100.0]
        is_outlier, stats, z_scores = detect_outliers_zscore(values, threshold=2.0)
        self.assertTrue(is_outlier[-1])
        self.assertGreater(abs(z_scores[-1]), 2.0)

    def test_process_csv(self) -> None:
        with tempfile.NamedTemporaryFile("w+", delete=False, suffix=".csv") as tmp:
            writer = csv.writer(tmp)
            writer.writerow(["id", "age", "income"])
            writer.writerow([1, 25, 50000])
            writer.writerow([2, 26, 52000])
            writer.writerow([3, 27, 51000])
            writer.writerow([4, 28, 49000])
            writer.writerow([5, 29, 53000])
            writer.writerow([6, 30, 1000000])  # outlier income
            tmp_path = Path(tmp.name)

        try:
            report = process_csv(tmp_path, method="iqr", threshold=1.5)
            self.assertEqual(report["method"], "iqr")
            self.assertIn("income", report["summary"])
            self.assertEqual(report["summary"]["income"]["outlier_count"], 1)
            self.assertEqual(len(report["outliers"]), 1)
            self.assertEqual(report["outliers"][0]["column"], "income")
            self.assertEqual(report["outliers"][0]["value"], 1000000.0)
        finally:
            if tmp_path.exists():
                tmp_path.unlink()


class TestOutlierDetectorEdges(unittest.TestCase):
    """Edge-case tests for detection helpers and end-to-end CLI behaviour."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def _write_csv(self, name: str, rows: List[List[object]]) -> Path:
        path = self.root / name
        with open(path, "w", encoding="utf-8", newline="") as f:
            csv.writer(f).writerows(rows)
        return path

    def test_calculate_percentile_degenerate_inputs(self) -> None:
        self.assertEqual(calculate_percentile([], 50.0), 0.0)
        self.assertEqual(calculate_percentile([42.0], 25.0), 42.0)
        # A percentile above 100 clamps to the largest sorted value.
        self.assertEqual(calculate_percentile([1.0, 2.0], 120.0), 2.0)

    def test_detect_outliers_iqr_empty_input(self) -> None:
        is_outlier, stats = detect_outliers_iqr([])
        self.assertEqual(is_outlier, [])
        self.assertEqual(stats, {})

    def test_detect_outliers_zscore_empty_input(self) -> None:
        is_outlier, stats, z_scores = detect_outliers_zscore([])
        self.assertEqual((is_outlier, stats, z_scores), ([], {}, []))

    def test_detect_outliers_zscore_zero_variance(self) -> None:
        is_outlier, stats, z_scores = detect_outliers_zscore([5.0, 5.0, 5.0])
        self.assertEqual(is_outlier, [False, False, False])
        self.assertEqual(z_scores, [0.0, 0.0, 0.0])
        self.assertEqual(stats["std_dev"], 0.0)

    def test_process_csv_empty_file_reports_error(self) -> None:
        path = self._write_csv("empty.csv", [["col_a"]])
        report = process_csv(path)
        self.assertIn("error", report)
        self.assertEqual(report["outliers"], [])

    def test_process_csv_zscore_with_column_filter_and_noise(self) -> None:
        path = self._write_csv(
            "sensor.csv",
            [
                ["reading", "label"],
                [10, "ok"],
                [12, "ok"],
                [11, "ok"],
                [13, "ok"],
                [12, "ok"],
                [200, "spike"],
                ["oops", "text"],
            ],
        )
        report = process_csv(
            path,
            target_columns=["reading", "not_a_column"],
            method="zscore",
            threshold=1.5,
        )
        self.assertEqual(report["method"], "zscore")
        # Unknown columns are ignored and non-numeric cells are skipped.
        self.assertEqual(list(report["summary"].keys()), ["reading"])
        self.assertEqual(report["summary"]["reading"]["valid_numeric_rows"], 6)
        self.assertEqual(report["summary"]["reading"]["outlier_count"], 1)

        outlier = report["outliers"][0]
        self.assertEqual(outlier["column"], "reading")
        self.assertEqual(outlier["value"], 200.0)
        self.assertGreater(outlier["z_score"], 1.5)

    def test_process_csv_non_numeric_column_is_skipped(self) -> None:
        path = self._write_csv(
            "text.csv",
            [["notes"], ["alpha"], ["beta"]],
        )
        report = process_csv(path)
        self.assertEqual(report["summary"], {})
        self.assertEqual(report["outliers"], [])

    def test_print_report_renders_summary_and_outliers(self) -> None:
        path = self._write_csv(
            "vals.csv",
            [["v"], [10], [11], [12], [11], [500]],
        )
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            print_report(process_csv(path))
        output = buf.getvalue()
        self.assertIn("Outlier Detection Report", output)
        self.assertIn("Column Summary:", output)
        self.assertIn("Flagged Outliers Total: 1", output)
        self.assertIn("bound=upper", output)

    def test_print_report_zscore_variant(self) -> None:
        path = self._write_csv(
            "vals.csv",
            [["v"], [10], [11], [12], [11], [500]],
        )
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            print_report(process_csv(path, method="zscore", threshold=1.5))
        self.assertIn("z_score=", buf.getvalue())

    def test_print_report_limits_preview_to_fifty_rows(self) -> None:
        outliers = [
            {
                "row_number": i,
                "column": "v",
                "value": float(i),
                "bound_exceeded": "upper",
                "distance_from_bound": 1.0,
            }
            for i in range(1, 56)
        ]
        summary = {
            "v": {
                "total_rows": 60,
                "valid_numeric_rows": 55,
                "outlier_count": 55,
                "outlier_percentage": 100.0,
                "stats": {},
            }
        }
        report = {
            "file": "x.csv",
            "method": "iqr",
            "threshold": 1.5,
            "summary": summary,
            "outliers": outliers,
        }
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            print_report(report)
        self.assertIn("... and 5 more outliers.", buf.getvalue())

    def test_print_report_without_numeric_columns(self) -> None:
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            print_report(
                {
                    "file": "x.csv",
                    "method": "iqr",
                    "threshold": 1.5,
                    "summary": {},
                    "outliers": [],
                }
            )
        self.assertIn("No numeric columns evaluated.", buf.getvalue())

    def test_parse_args_defaults(self) -> None:
        parsed = parse_args(["data.csv"])
        self.assertEqual(parsed.input_csv, Path("data.csv"))
        self.assertIsNone(parsed.column)
        self.assertEqual(parsed.method, "iqr")
        self.assertIsNone(parsed.threshold)
        self.assertIsNone(parsed.output)

    def test_parse_args_custom_options(self) -> None:
        parsed = parse_args(["data.csv", "-c", "a", "b", "-m", "zscore", "-t", "2.5"])
        self.assertEqual(parsed.column, ["a", "b"])
        self.assertEqual(parsed.method, "zscore")
        self.assertEqual(parsed.threshold, 2.5)

    def test_main_missing_input_returns_error(self) -> None:
        ret = main([str(self.root / "nope.csv")])
        self.assertEqual(ret, 1)

    def test_main_json_report_output(self) -> None:
        csv_path = self._write_csv(
            "vals.csv",
            [["v"], [10], [11], [12], [11], [500]],
        )
        out_path = self.root / "nested" / "report.json"
        ret = main(["-c", "v", "-o", str(out_path), str(csv_path)])
        self.assertEqual(ret, 0)
        data = json.loads(out_path.read_text(encoding="utf-8"))
        self.assertEqual(data["method"], "iqr")
        self.assertEqual(len(data["outliers"]), 1)

    def test_main_csv_report_output(self) -> None:
        csv_path = self._write_csv(
            "vals.csv",
            [["v"], [10], [11], [12], [11], [500]],
        )
        out_path = self.root / "report.csv"
        ret = main(["-o", str(out_path), str(csv_path)])
        self.assertEqual(ret, 0)
        with open(out_path, encoding="utf-8", newline="") as f:
            rows = list(csv.DictReader(f))
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["column"], "v")
        self.assertEqual(rows[0]["bound_exceeded"], "upper")


if __name__ == "__main__":
    unittest.main()
