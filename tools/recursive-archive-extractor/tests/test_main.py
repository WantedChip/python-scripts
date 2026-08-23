"""Unit tests for the recursive archive extractor."""

import io
import pathlib
import tarfile
import tempfile
import unittest
import zipfile
from typing import Any, Optional
from unittest.mock import MagicMock, patch

from main import RecursiveArchiveExtractor, build_parser, main


def _fake_encrypted_zip(content: bytes, correct_pwd: bytes) -> Any:
    """Build a ZipFile stand-in that demands a password on open()."""

    class FakeEncryptedZip:
        """Mimics zipfile.ZipFile for a single encrypted member."""

        def __enter__(self) -> "FakeEncryptedZip":
            return self

        def __exit__(self, *_exc: object) -> None:
            return None

        def infolist(self) -> list:
            info = MagicMock()
            info.filename = "secret.txt"
            info.is_dir.return_value = False
            info.file_size = len(content)
            return [info]

        def open(self, _member: Any, pwd: Optional[bytes] = None) -> io.BytesIO:
            if pwd != correct_pwd:
                raise RuntimeError("Bad password for file secret.txt")
            return io.BytesIO(content)

    return FakeEncryptedZip


class TestRecursiveArchiveExtractor(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.work_dir = pathlib.Path(self.temp_dir.name)
        self.out_dir = self.work_dir / "output"

        # Create inner zip archive
        self.inner_zip_path = self.work_dir / "inner.zip"
        with zipfile.ZipFile(self.inner_zip_path, "w") as zf:
            zf.writestr("inner_file.txt", "Content of inner file")

        # Create outer zip archive containing inner zip
        self.outer_zip_path = self.work_dir / "outer.zip"
        with zipfile.ZipFile(self.outer_zip_path, "w") as zf:
            zf.writestr("outer_file.txt", "Content of outer file")
            with open(self.inner_zip_path, "rb") as inner_f:
                zf.writestr("nested/inner.zip", inner_f.read())

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_recursive_extraction(self):
        extractor = RecursiveArchiveExtractor(
            output_dir=self.out_dir, max_depth=3, max_size_mb=10, max_files=100
        )
        metrics = extractor.process_recursive(self.outer_zip_path)

        self.assertGreaterEqual(metrics.total_files, 2)
        self.assertEqual(len(metrics.errors), 0)

        # Check extracted files exist
        extracted_inner = list(self.out_dir.rglob("inner_file.txt"))
        self.assertTrue(len(extracted_inner) > 0)

    def test_password_protected_zip(self):
        encrypted_zip_path = self.work_dir / "encrypted.zip"
        password = "secret_pass_123"

        with zipfile.ZipFile(encrypted_zip_path, "w") as zf:
            zf.setpassword(password.encode("utf-8"))
            zf.writestr(
                "secret.txt",
                b"Secret contents requiring decryption",
                compress_type=zipfile.ZIP_DEFLATED,
            )

        extractor = RecursiveArchiveExtractor(
            output_dir=self.out_dir, passwords=["wrong1", password, "wrong2"]
        )
        metrics = extractor.process_recursive(encrypted_zip_path)
        self.assertEqual(len(metrics.errors), 0)

        extracted_secret = list(self.out_dir.rglob("secret.txt"))
        self.assertTrue(len(extracted_secret) > 0)

    def test_archive_bomb_limit_file_count(self):
        # Limit max_files to 1 file
        extractor = RecursiveArchiveExtractor(
            output_dir=self.out_dir, max_depth=3, max_files=1
        )
        metrics = extractor.process_recursive(self.outer_zip_path)
        # Should record bomb exception in errors list
        self.assertTrue(any("Exceeded max file count" in err for err in metrics.errors))

    def test_safe_path_traversal(self):
        target_dir = self.work_dir / "target"
        unsafe_path = target_dir / ".." / "outside.txt"
        safe_path = target_dir / "sub" / "inside.txt"

        self.assertFalse(
            RecursiveArchiveExtractor.is_safe_path(target_dir, unsafe_path)
        )
        self.assertTrue(RecursiveArchiveExtractor.is_safe_path(target_dir, safe_path))


class TestZipExtractionSecurity(unittest.TestCase):
    """Test suite for zip security controls and password retries."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.work = pathlib.Path(self.temp_dir.name)
        self.out_dir = self.work / "out"

    def _extractor(self, **kwargs: Any) -> RecursiveArchiveExtractor:
        defaults: dict = {"output_dir": self.out_dir, "max_depth": 3}
        defaults.update(kwargs)
        return RecursiveArchiveExtractor(**defaults)

    def test_wrong_passwords_only_record_failure(self) -> None:
        """When no supplied password works the failure is recorded."""
        archive = self.work / "locked.zip"
        fake_cls = _fake_encrypted_zip(b"top secret", b"s3cret")
        extractor = self._extractor(passwords=["nope1", "nope2"])
        with patch("zipfile.ZipFile", MagicMock(return_value=fake_cls())):
            ok = extractor.extract_archive(archive, self.out_dir / "d1")
        self.assertFalse(ok)
        self.assertTrue(any("Failed to decrypt" in e for e in extractor.metrics.errors))
        # No partial file may be left behind.
        self.assertFalse((self.out_dir / "d1" / "secret.txt").exists())

    def test_password_retry_until_correct(self) -> None:
        """Wrong passwords are skipped; the right one extracts content."""
        archive = self.work / "vault.zip"
        fake_cls = _fake_encrypted_zip(b"top secret", b"s3cret")
        extractor = self._extractor(passwords=["wrong", "s3cret", "also-wrong"])
        with patch("zipfile.ZipFile", MagicMock(return_value=fake_cls())):
            metrics = extractor.process_recursive(archive)
        self.assertEqual(metrics.total_files, 1)
        extracted = list(self.out_dir.rglob("secret.txt"))
        self.assertEqual(len(extracted), 1)
        self.assertEqual(extracted[0].read_bytes(), b"top secret")

    def test_path_traversal_member_is_skipped(self) -> None:
        archive = self.work / "evil.zip"
        with zipfile.ZipFile(archive, "w") as zf:
            zf.writestr("../escaped.txt", "malicious")

        extractor = self._extractor()
        metrics = extractor.process_recursive(archive)
        self.assertEqual(metrics.total_files, 0)
        self.assertFalse((self.work / "escaped.txt").exists())

    def test_directory_entries_create_folders(self) -> None:
        archive = self.work / "dirs.zip"
        with zipfile.ZipFile(archive, "w") as zf:
            zf.writestr("subfolder/", "")

        extractor = self._extractor()
        extractor.process_recursive(archive)
        subfolders = [p for p in self.out_dir.rglob("*") if p.is_dir()]
        self.assertTrue(any(p.name == "subfolder" for p in subfolders))

    def test_size_bomb_limit_triggers(self) -> None:
        archive = self.work / "bomb.zip"
        with zipfile.ZipFile(archive, "w") as zf:
            zf.writestr("big.bin", b"x" * 64)

        extractor = self._extractor(max_size_mb=0)
        metrics = extractor.process_recursive(archive)
        self.assertTrue(any("Exceeded max size threshold" in e for e in metrics.errors))

    def test_corrupt_zip_records_error(self) -> None:
        archive = self.work / "broken.zip"
        archive.write_bytes(b"this is not a zip archive at all")
        extractor = self._extractor()
        metrics = extractor.process_recursive(archive)
        self.assertTrue(any("Error extracting ZIP" in e for e in metrics.errors))

    def test_non_password_zip_error_is_reraised(self) -> None:
        """Corruption during extraction is recorded, not mistaken for auth."""
        archive = self.work / "crcfail.zip"

        class CrcFailZip:
            """ZipFile stand-in failing with a CRC-style error."""

            def __enter__(self) -> "CrcFailZip":
                return self

            def __exit__(self, *_exc: object) -> None:
                return None

            def infolist(self) -> list:
                info = MagicMock()
                info.filename = "data.bin"
                info.is_dir.return_value = False
                info.file_size = 8
                return [info]

            def open(self, _member: Any, pwd: Any = None) -> Any:
                raise zipfile.BadZipFile("Bad CRC-32 for file data.bin")

        extractor = self._extractor(passwords=["whatever"])
        with patch("zipfile.ZipFile", MagicMock(return_value=CrcFailZip())):
            ok = extractor.extract_archive(archive, self.out_dir / "d1")
        self.assertFalse(ok)
        self.assertTrue(
            any("Error extracting ZIP" in e for e in extractor.metrics.errors)
        )


class TestTarExtraction(unittest.TestCase):
    """Test suite for tar/tar.gz handling."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.work = pathlib.Path(self.temp_dir.name)
        self.out_dir = self.work / "out"

    def _make_tar_gz(self, name: str = "bundle.tar.gz") -> pathlib.Path:
        path = self.work / name
        with tarfile.open(path, "w:gz") as tf:
            data = b"tar payload"
            info = tarfile.TarInfo("docs/readme.txt")
            info.size = len(data)
            tf.addfile(info, io.BytesIO(data))
            dir_info = tarfile.TarInfo("emptydir")
            dir_info.type = tarfile.DIRTYPE
            tf.addfile(dir_info)
        return path

    def test_tar_gz_extraction(self) -> None:
        extractor = RecursiveArchiveExtractor(output_dir=self.out_dir)
        metrics = extractor.process_recursive(self._make_tar_gz())
        self.assertEqual(metrics.total_files, 1)
        readme = list(self.out_dir.rglob("readme.txt"))
        self.assertEqual(len(readme), 1)
        self.assertEqual(readme[0].read_bytes(), b"tar payload")

    def test_tar_path_traversal_is_skipped(self) -> None:
        path = self.work / "trav.tar"
        with tarfile.open(path, "w") as tf:
            info = tarfile.TarInfo("../tar_escaped.txt")
            info.size = 4
            tf.addfile(info, io.BytesIO(b"evil"))

        extractor = RecursiveArchiveExtractor(output_dir=self.out_dir)
        metrics = extractor.process_recursive(path)
        self.assertEqual(metrics.total_files, 0)
        self.assertFalse((self.work / "tar_escaped.txt").exists())

    def test_corrupt_tar_records_error(self) -> None:
        path = self.work / "junk.tar"
        path.write_bytes(b"not a tar by any stretch")
        extractor = RecursiveArchiveExtractor(output_dir=self.out_dir)
        metrics = extractor.process_recursive(path)
        self.assertTrue(any("Error extracting TAR" in e for e in metrics.errors))

    def test_tar_bomb_limit_propagates(self) -> None:
        path = self.work / "heavy.tar"
        with tarfile.open(path, "w") as tf:
            data = b"z" * 64
            info = tarfile.TarInfo("big.bin")
            info.size = len(data)
            tf.addfile(info, io.BytesIO(data))

        extractor = RecursiveArchiveExtractor(output_dir=self.out_dir, max_size_mb=0)
        metrics = extractor.process_recursive(path)
        self.assertTrue(any("Exceeded max size threshold" in e for e in metrics.errors))


class TestRoutingAndLimits(unittest.TestCase):
    """Test suite for archive routing, dedupe, and depth limits."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.work = pathlib.Path(self.temp_dir.name)
        self.out_dir = self.work / "out"

        self.plain_zip = self.work / "plain.zip"
        with zipfile.ZipFile(self.plain_zip, "w") as zf:
            zf.writestr("content.txt", "hello")

    def test_same_archive_not_extracted_twice(self) -> None:
        extractor = RecursiveArchiveExtractor(output_dir=self.out_dir)
        dest = self.out_dir / "run"
        self.assertTrue(extractor.extract_archive(self.plain_zip, dest))
        self.assertFalse(extractor.extract_archive(self.plain_zip, dest))

    def test_unknown_extension_rejected(self) -> None:
        fake = self.work / "payload.rar"
        fake.write_bytes(b"Rar!")
        extractor = RecursiveArchiveExtractor(output_dir=self.out_dir)
        self.assertFalse(extractor.extract_archive(fake, self.out_dir / "rar"))

    def test_max_depth_zero_skips_extraction(self) -> None:
        extractor = RecursiveArchiveExtractor(output_dir=self.out_dir, max_depth=0)
        metrics = extractor.process_recursive(self.plain_zip)
        self.assertEqual(metrics.total_files, 0)
        self.assertFalse(any(self.out_dir.rglob("*")))

    def test_failed_root_extraction_returns_metrics(self) -> None:
        bogus = self.work / "bogus.zip"
        bogus.write_bytes(b"garbage")
        extractor = RecursiveArchiveExtractor(output_dir=self.out_dir)
        metrics = extractor.process_recursive(bogus)
        self.assertEqual(len(metrics.errors), 1)

    def test_nested_bomb_breaks_nested_scan(self) -> None:
        """A bomb nested one level deep stops further nested processing."""
        inner = io.BytesIO()
        with zipfile.ZipFile(inner, "w") as zf:
            zf.writestr("in1.txt", "a")
            zf.writestr("in2.txt", "bb")
        outer_path = self.work / "outer.zip"
        with zipfile.ZipFile(outer_path, "w") as zf:
            zf.writestr("top.txt", "fine")
            zf.writestr("inner.zip", inner.getvalue())

        extractor = RecursiveArchiveExtractor(output_dir=self.out_dir, max_files=2)
        metrics = extractor.process_recursive(outer_path)
        # top.txt + inner.zip consumed both allowed slots.
        self.assertEqual(metrics.total_files, 2)
        self.assertTrue(any("Exceeded max file count" in e for e in metrics.errors))


class TestCliEntryPoint(unittest.TestCase):
    """End-to-end tests for build_parser and main()."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.work = pathlib.Path(self.temp_dir.name)

        self.zip_path = self.work / "app.zip"
        with zipfile.ZipFile(self.zip_path, "w") as zf:
            zf.writestr("app/main.py", "print('hi')")

    def test_build_parser_flags_and_defaults(self) -> None:
        parser = build_parser()
        args = parser.parse_args([str(self.zip_path), str(self.work / "o")])
        self.assertIsNone(args.password)
        self.assertEqual(args.max_depth, 5)
        self.assertEqual(args.max_size_mb, 1024)
        self.assertEqual(args.max_files, 10000)

        full = parser.parse_args(
            [
                str(self.zip_path),
                str(self.work / "o"),
                "--password",
                "one",
                "--password",
                "two",
                "--max-depth",
                "2",
                "--max-size-mb",
                "10",
                "--max-files",
                "20",
            ]
        )
        self.assertEqual(full.password, ["one", "two"])
        self.assertEqual(full.max_depth, 2)
        self.assertEqual(full.max_size_mb, 10)
        self.assertEqual(full.max_files, 20)

    def test_main_missing_archive_returns_one(self) -> None:
        rc = main([str(self.work / "missing.zip"), str(self.work / "o")])
        self.assertEqual(rc, 1)

    def test_main_successful_run_returns_zero(self) -> None:
        out_dir = self.work / "extracted"
        rc = main([str(self.zip_path), str(out_dir)])
        self.assertEqual(rc, 0)
        self.assertTrue((out_dir / "depth_1_app" / "app" / "main.py").exists())

    def test_main_passwords_merge_cli_and_file(self) -> None:
        """CLI passwords and wordlist entries are combined in order."""
        words_file = self.work / "words.txt"
        words_file.write_text("alpha\n\nbeta\n", encoding="utf-8")

        captured: dict = {}
        real_cls = RecursiveArchiveExtractor

        class SpyExtractor(real_cls):
            def __init__(self, *args: Any, **kwargs: Any):
                captured["passwords"] = kwargs.get("passwords")
                super().__init__(*args, **kwargs)

        with patch("main.RecursiveArchiveExtractor", SpyExtractor):
            rc = main(
                [
                    str(self.zip_path),
                    str(self.work / "o"),
                    "--password",
                    "cli_pass",
                    "--passwords-file",
                    str(words_file),
                ]
            )
        self.assertEqual(rc, 0)
        self.assertEqual(captured["passwords"], ["cli_pass", "alpha", "beta"])

    def test_main_password_file_read_failure_is_tolerated(self) -> None:
        """An unreadable wordlist logs an error but does not abort."""
        words_file = self.work / "locked_words.txt"
        words_file.write_text("alpha\n", encoding="utf-8")

        real_open = open

        def selective_open(file: Any, *args: Any, **kwargs: Any) -> Any:
            if str(file) == str(words_file):
                raise OSError("wordlist unreadable")
            return real_open(file, *args, **kwargs)

        with patch("builtins.open", side_effect=selective_open):
            rc = main(
                [
                    str(self.zip_path),
                    str(self.work / "o"),
                    "--passwords-file",
                    str(words_file),
                ]
            )
        self.assertEqual(rc, 0)
        self.assertTrue((self.work / "o" / "depth_1_app" / "app" / "main.py").exists())

    def test_main_error_run_returns_one(self) -> None:
        broken = self.work / "broken.zip"
        broken.write_bytes(b"definitely not zip data")
        rc = main([str(broken), str(self.work / "o")])
        self.assertEqual(rc, 1)


if __name__ == "__main__":
    unittest.main()
