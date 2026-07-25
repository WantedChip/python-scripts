"""Unit tests for copy-drift main.py."""

import tempfile
import time
import unittest
from pathlib import Path

from main import (
    compute_ngrams,
    detect_copy_drift,
    extract_blocks_from_file,
    jaccard_similarity,
    tokenize_code,
)


class TestCopyDrift(unittest.TestCase):
    """Tests for structural similarity and copy drift detection."""

    def test_tokenization_and_similarity(self) -> None:
        code1 = (
            "def calculate_total(price, tax):\n"
            "    subtotal = price * 1.1\n"
            "    return subtotal + tax"
        )
        code2 = (
            "def compute_total(cost, fee):\n"
            "    subtotal = cost * 1.1\n"
            "    return subtotal + fee"
        )
        t1 = tokenize_code(code1)
        t2 = tokenize_code(code2)
        ng1 = compute_ngrams(t1)
        ng2 = compute_ngrams(t2)
        sim = jaccard_similarity(ng1, ng2)
        self.assertGreater(sim, 0.70)

    def test_drift_detection_between_files(self) -> None:
        code1 = """def process_data(records):
    results = []
    for item in records:
        if item.is_valid():
            results.append(item.transform())
    return results
"""
        code2 = """def process_items(items):
    results = []
    for item in items:
        if item.is_valid():
            results.append(item.transform())
            logger.info("Processed item")
    return results
"""
        with tempfile.TemporaryDirectory() as tmp_dir:
            p1 = Path(tmp_dir) / "file1.py"
            p2 = Path(tmp_dir) / "file2.py"

            p1.write_text(code1, encoding="utf-8")
            time.sleep(0.05)  # Ensure mtime difference
            p2.write_text(code2, encoding="utf-8")

            blocks1 = extract_blocks_from_file(p1, min_lines=3)
            blocks2 = extract_blocks_from_file(p2, min_lines=3)

            reports = detect_copy_drift(blocks1 + blocks2, similarity_threshold=0.60)
            self.assertEqual(len(reports), 1)
            self.assertIn("file2.py", reports[0].updated_file)
            self.assertIn("file1.py", reports[0].outdated_file)


if __name__ == "__main__":
    unittest.main()
