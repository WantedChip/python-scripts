"""Unit tests for generated-file-check tool."""

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from main import (
    ManifestEntry,
    check_manifest_entry,
    compute_file_hash,
    is_file_generated,
    load_manifest,
)


class TestGeneratedFileCheck(unittest.TestCase):
    """Test suite for generated-file-check functionality."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)

        self.src = self.root / "src.txt"
        self.src.write_text("source content", encoding="utf-8")

        self.gen = self.root / "gen.txt"
        self.gen.write_text(
            "// DO NOT EDIT - Auto-generated\ngen content", encoding="utf-8"
        )

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_is_file_generated(self) -> None:
        self.assertTrue(is_file_generated(self.gen))
        self.assertFalse(is_file_generated(self.src))

    def test_compute_file_hash(self) -> None:
        h = compute_file_hash(self.src)
        expected = hashlib.sha256(b"source content").hexdigest()
        self.assertEqual(h, expected)

    def test_check_manifest_entry_hash_matching(self) -> None:
        gen_hash = compute_file_hash(self.gen)
        entry = ManifestEntry(
            source_path=Path("src.txt"),
            generated_path=Path("gen.txt"),
            expected_hash=gen_hash,
        )
        res = check_manifest_entry(entry, self.root)
        self.assertTrue(res.is_in_sync)

    def test_check_manifest_entry_hash_mismatch(self) -> None:
        entry = ManifestEntry(
            source_path=Path("src.txt"),
            generated_path=Path("gen.txt"),
            expected_hash="invalid_hash_value",
        )
        res = check_manifest_entry(entry, self.root)
        self.assertFalse(res.is_in_sync)

    def test_load_manifest(self) -> None:
        manifest_file = self.root / ".generated-manifest.json"
        manifest_file.write_text(
            json.dumps(
                {
                    "mappings": [
                        {
                            "source": "src.txt",
                            "generated": "gen.txt",
                            "command": "cp {source} {output}",
                        }
                    ]
                }
            ),
            encoding="utf-8",
        )
        entries = load_manifest(manifest_file)
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0].source_path, Path("src.txt"))


if __name__ == "__main__":
    unittest.main()
