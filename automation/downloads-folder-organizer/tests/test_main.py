import json
import shutil
import tempfile
import unittest
from pathlib import Path

from main import (
    build_organize_plan,
    categorize_file,
    execute_organize_plan,
    load_category_rules,
    resolve_collision,
    rollback_organize,
)


class TestDownloadsFolderOrganizer(unittest.TestCase):
    def setUp(self):
        self.test_dir = Path(tempfile.mkdtemp())
        self.rules = load_category_rules()

    def tearDown(self):
        shutil.rmtree(self.test_dir)

    def test_categorize_file(self):
        self.assertEqual(categorize_file(Path("document.pdf"), self.rules), "Documents")
        self.assertEqual(categorize_file(Path("photo.jpg"), self.rules), "Images")
        self.assertEqual(categorize_file(Path("script.py"), self.rules), "Code")
        self.assertEqual(categorize_file(Path("archive.zip"), self.rules), "Archives")
        self.assertEqual(categorize_file(Path("unknown.xyz123"), self.rules), "Others")

    def test_custom_rules(self):
        config_path = self.test_dir / "custom_rules.json"
        config_data = {"Ebooks": [".epub", ".mobi"], "Cad": [".dwg"]}
        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(config_data, f)

        custom_rules = load_category_rules(config_path)
        self.assertIn("Ebooks", custom_rules)
        self.assertEqual(categorize_file(Path("book.epub"), custom_rules), "Ebooks")

    def test_resolve_collision(self):
        f1 = self.test_dir / "test.txt"
        f1.touch()

        collided = resolve_collision(f1)
        self.assertEqual(collided.name, "test_1.txt")

    def test_build_organize_plan_and_execute(self):
        f_pdf = self.test_dir / "report.pdf"
        f_img = self.test_dir / "avatar.png"
        f_pdf.write_text("pdf data")
        f_img.write_text("png data")

        plan = build_organize_plan(self.test_dir, self.rules)
        self.assertEqual(len(plan), 2)

        manifest_path = self.test_dir / "manifest.json"
        executed = execute_organize_plan(plan, manifest_path=manifest_path)

        self.assertEqual(len(executed), 2)
        self.assertTrue((self.test_dir / "Documents" / "report.pdf").exists())
        self.assertTrue((self.test_dir / "Images" / "avatar.png").exists())
        self.assertFalse(f_pdf.exists())

        # Test Rollback
        restored = rollback_organize(manifest_path)
        self.assertEqual(len(restored), 2)
        self.assertTrue(f_pdf.exists())
        self.assertTrue(f_img.exists())

    def test_date_subfolder_sorting(self):
        f_doc = self.test_dir / "notes.txt"
        f_doc.write_text("some notes")

        plan = build_organize_plan(
            self.test_dir, self.rules, by_date=True, date_format="%Y-%m"
        )
        self.assertEqual(len(plan), 1)
        target_path_str = str(plan[0].target)
        self.assertIn("Documents", target_path_str)


if __name__ == "__main__":
    unittest.main()
