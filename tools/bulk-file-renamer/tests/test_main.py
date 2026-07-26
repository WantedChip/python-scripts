import shutil
import tempfile
import unittest
from pathlib import Path

from main import (
    apply_case_format,
    build_rename_plan,
    check_collisions,
    execute_rename_plan,
    rollback_from_manifest,
)


class TestBulkFileRenamer(unittest.TestCase):
    def setUp(self):
        self.test_dir = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.test_dir)

    def test_apply_case_format(self):
        self.assertEqual(apply_case_format("hello_world", "upper"), "HELLO_WORLD")
        self.assertEqual(apply_case_format("HELLO WORLD", "lower"), "hello world")
        self.assertEqual(apply_case_format("hello world", "title"), "Hello World")
        self.assertEqual(apply_case_format("Hello World", "snake"), "hello_world")
        self.assertEqual(apply_case_format("hello_world", "camel"), "helloWorld")

    def test_build_rename_plan_regex_and_numbering(self):
        f1 = self.test_dir / "img_001.png"
        f2 = self.test_dir / "img_002.png"
        f1.touch()
        f2.touch()

        plan = build_rename_plan(
            directory=self.test_dir,
            match_pattern=r"img_(\d+)",
            replace_pattern=r"photo_\1",
            prefix="vacation_",
            number_start=10,
            number_format="{:02d}",
        )

        matched_items = [p for p in plan if p.matched]
        self.assertEqual(len(matched_items), 2)
        self.assertEqual(matched_items[0].target.name, "vacation_photo_001_10.png")
        self.assertEqual(matched_items[1].target.name, "vacation_photo_002_11.png")

    def test_check_collisions(self):
        f1 = self.test_dir / "fileA.txt"
        f2 = self.test_dir / "fileB.txt"
        f1.touch()
        f2.touch()

        # Both mapping to fileC.txt
        plan = build_rename_plan(
            directory=self.test_dir,
            match_pattern=r"file[AB]\.txt",
            replace_pattern="fileC.txt",
        )

        collisions = check_collisions(plan)
        self.assertTrue(len(collisions) > 0)

    def test_execute_and_rollback(self):
        f1 = self.test_dir / "doc1.txt"
        f2 = self.test_dir / "doc2.txt"
        f1.write_text("content 1")
        f2.write_text("content 2")

        manifest_path = self.test_dir / "manifest.json"

        plan = build_rename_plan(
            directory=self.test_dir,
            match_pattern=r"doc(\d+)\.txt",
            replace_pattern=r"report_\1.txt",
        )

        executed = execute_rename_plan(plan, manifest_path=manifest_path)
        self.assertEqual(len(executed), 2)
        self.assertTrue((self.test_dir / "report_1.txt").exists())
        self.assertFalse(f1.exists())

        # Test Rollback
        restored = rollback_from_manifest(manifest_path)
        self.assertEqual(len(restored), 2)
        self.assertTrue(f1.exists())
        self.assertTrue(f2.exists())
        self.assertEqual(f1.read_text(), "content 1")


if __name__ == "__main__":
    unittest.main()
