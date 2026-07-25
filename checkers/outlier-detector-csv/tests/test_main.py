"""Unit tests for Outlier Detector CSV tool."""

import csv
import tempfile
import unittest
from pathlib import Path

from main import (
    calculate_percentile,
    detect_outliers_iqr,
    detect_outliers_zscore,
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


if __name__ == "__main__":
    unittest.main()
