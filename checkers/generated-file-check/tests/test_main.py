"""Unit tests for generated-file-check tool."""

import contextlib
import hashlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from typing import Tuple
from unittest import mock

import main as main_module
from main import (
    ManifestEntry,
    check_manifest_entry,
    compute_file_hash,
    is_file_generated,
    load_manifest,
    main,
    scan_directory_for_generated,
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


class TestEdgeCases(unittest.TestCase):
    """Tests for missing files, unreadable paths, and header scanning."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_is_file_generated_missing_or_directory(self) -> None:
        """Non-files and unreadable paths are not 'generated'."""
        self.assertFalse(is_file_generated(self.root / "ghost.txt"))
        self.assertFalse(is_file_generated(self.root))

    def test_is_file_generated_unreadable_content(self) -> None:
        """Read errors are swallowed and reported as not generated."""
        target = self.root / "locked.txt"
        target.write_text("@generated", encoding="utf-8")
        with mock.patch.object(Path, "read_text", side_effect=OSError("cannot read")):
            self.assertFalse(is_file_generated(target))

    def test_compute_file_hash_missing_file(self) -> None:
        """Hashing a non-existent file yields the empty sentinel."""
        self.assertEqual(compute_file_hash(self.root / "nope.bin"), "")

    def test_manifest_entry_reports_missing_files(self) -> None:
        """Missing source or generated artifacts are flagged distinctly."""
        res = check_manifest_entry(
            ManifestEntry(Path("gone.src"), Path("gen.txt")), self.root
        )
        self.assertFalse(res.is_in_sync)
        self.assertIn("Source file missing", res.status_message)

        (self.root / "src.txt").write_text("data", encoding="utf-8")
        res = check_manifest_entry(
            ManifestEntry(Path("src.txt"), Path("gone.gen")), self.root
        )
        self.assertFalse(res.is_in_sync)
        self.assertIn("Generated file missing", res.status_message)

    def test_load_manifest_missing_file_returns_empty(self) -> None:
        """A missing manifest file parses to zero entries."""
        self.assertEqual(load_manifest(self.root / "none.json"), [])

    def test_scan_directory_finds_headers_skips_hidden(self) -> None:
        """Header scan finds visible @generated files, skips hidden dirs."""
        gen_visible = self.root / "build" / "out.py"
        gen_visible.parent.mkdir()
        gen_visible.write_text("# @generated by tool\nx = 1", encoding="utf-8")

        clean = self.root / "hand.py"
        clean.write_text("# hand written\ny = 2", encoding="utf-8")

        hidden = self.root / ".cache" / "stale.py"
        hidden.parent.mkdir()
        hidden.write_text("# DO NOT EDIT\nz = 3", encoding="utf-8")

        found = scan_directory_for_generated(self.root)
        self.assertIn(gen_visible, found)
        self.assertNotIn(clean, found)
        self.assertNotIn(hidden, found)


class TestGeneratorReruns(unittest.TestCase):
    """Tests for generator-command verification (subprocess mocked)."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.src = self.root / "src.txt"
        self.gen = self.root / "gen.txt"

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def _entry(self, in_sync: bool) -> ManifestEntry:
        """Build a manifest entry with a copy-style generator command."""
        if in_sync:
            content = "same output"
        else:
            content = "stale output"
        self.src.write_text("fresh source", encoding="utf-8")
        self.gen.write_text(content, encoding="utf-8")
        return ManifestEntry(
            source_path=Path("src.txt"),
            generated_path=Path("gen.txt"),
            generator_command="copy|{source}|{output}",
        )

    @staticmethod
    def _fake_run(writes_output: bool, returncode: int = 0):
        """Build a subprocess.run replacement that emulates a copier."""

        def _run(cmd: str, **_kwargs):
            _, src_str, out_str = cmd.split("|")
            if writes_output:
                Path(out_str).write_text("fresh source", encoding="utf-8")
            proc = mock.Mock()
            proc.returncode = returncode
            proc.stderr = "boom" if returncode else ""
            return proc

        return _run

    def test_generator_rerun_in_sync(self) -> None:
        """Regenerated output matching the artifact counts as in sync."""
        entry = self._entry(in_sync=False)
        # Generator copies source to output; source matches committed gen.
        self.gen.write_text("fresh source", encoding="utf-8")
        with mock.patch.object(
            main_module.subprocess,
            "run",
            side_effect=self._fake_run(writes_output=True),
        ):
            res = check_manifest_entry(entry, self.root)
        self.assertTrue(res.is_in_sync)
        self.assertIn("generator rerun", res.status_message)

    def test_generator_rerun_out_of_sync(self) -> None:
        """Divergent regenerated output marks the artifact out of sync."""
        entry = self._entry(in_sync=True)
        with mock.patch.object(
            main_module.subprocess,
            "run",
            side_effect=self._fake_run(writes_output=True),
        ):
            res = check_manifest_entry(entry, self.root)
        self.assertFalse(res.is_in_sync)
        self.assertIn("out of sync", res.status_message)

    def test_generator_failure_reported(self) -> None:
        """Non-zero generator exits are surfaced with stderr."""
        entry = self._entry(in_sync=True)
        with mock.patch.object(
            main_module.subprocess,
            "run",
            side_effect=self._fake_run(writes_output=False, returncode=2),
        ):
            res = check_manifest_entry(entry, self.root)
        self.assertFalse(res.is_in_sync)
        self.assertIn("Generator failed with code 2", res.status_message)

    def test_generator_without_output_reported(self) -> None:
        """Generators that produce no file are reported."""
        entry = self._entry(in_sync=True)
        with mock.patch.object(
            main_module.subprocess,
            "run",
            side_effect=self._fake_run(writes_output=False),
        ):
            res = check_manifest_entry(entry, self.root)
        self.assertFalse(res.is_in_sync)
        self.assertIn("did not output", res.status_message)

    def test_generator_exception_reported(self) -> None:
        """Generator invocation crashes become Generator error results."""
        entry = self._entry(in_sync=True)
        with mock.patch.object(
            main_module.subprocess,
            "run",
            side_effect=ValueError("spawn failed"),
        ):
            res = check_manifest_entry(entry, self.root)
        self.assertFalse(res.is_in_sync)
        self.assertIn("Generator error", res.status_message)


class TestMainCli(unittest.TestCase):
    """End-to-end tests for the command-line entrypoint."""

    def _write_repo(self, tmpdir: str) -> Tuple[Path, Path]:
        """Create a repo dir with manifest + matched generated pair."""
        root = Path(tmpdir)
        src = root / "src.txt"
        gen = root / "gen.txt"
        src.write_text("payload", encoding="utf-8")
        gen.write_text("# @generated\npayload", encoding="utf-8")
        manifest = root / ".generated-manifest.json"
        manifest.write_text(
            json.dumps(
                {
                    "mappings": [
                        {
                            "source": "src.txt",
                            "generated": "gen.txt",
                            "hash": compute_file_hash(gen),
                        }
                    ]
                }
            ),
            encoding="utf-8",
        )
        return root, gen

    def test_main_in_sync_returns_zero(self) -> None:
        """Matched hashes plus header scan yield SUCCESS and exit 0."""
        with tempfile.TemporaryDirectory() as tmpdir:
            root, _ = self._write_repo(tmpdir)
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                code = main(["--root", str(root), "--scan-headers"])
        out = buf.getvalue()
        self.assertEqual(code, 0)
        self.assertIn("Loading manifest from", out)
        self.assertIn("Detected generated header: gen.txt", out)
        self.assertIn("SUCCESS: All generated files are in sync.", out)

    def test_main_out_of_sync_returns_one(self) -> None:
        """Hash drift is summarized as FAILURE with exit 1."""
        with tempfile.TemporaryDirectory() as tmpdir:
            root, gen = self._write_repo(tmpdir)
            gen.write_text("# @generated\nDRIFTED", encoding="utf-8")
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                code = main(["--root", str(root)])
        self.assertEqual(code, 1)
        self.assertIn("OUT-OF-SYNC", buf.getvalue())
        self.assertIn("FAILURE: 1 generated file(s) out of sync!", buf.getvalue())

    def test_main_without_manifest_reports_nothing_checked(self) -> None:
        """Repositories without a manifest still exit cleanly."""
        with tempfile.TemporaryDirectory() as tmpdir:
            empty = Path(tmpdir) / "empty"
            empty.mkdir()
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                code = main(["--root", str(empty)])
        self.assertEqual(code, 0)
        self.assertIn("No manifest mappings checked.", buf.getvalue())

    def test_main_empty_mappings_list(self) -> None:
        """An existing manifest without mappings checks nothing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / ".generated-manifest.json").write_text(
                json.dumps({"mappings": []}), encoding="utf-8"
            )
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                code = main(["--root", str(root)])
        self.assertEqual(code, 0)
        self.assertIn("No manifest mappings checked.", buf.getvalue())


if __name__ == "__main__":
    unittest.main()
