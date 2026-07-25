"""Unit tests for artifact-recipe main.py."""

import tempfile
import unittest
from pathlib import Path

from main import (
    compute_file_hash,
    create_recipe,
    explain_artifact,
    get_recipe_path_for_artifact,
    save_recipe,
)


class TestArtifactRecipe(unittest.TestCase):
    """Tests for recipe creation and staleness explanation."""

    def test_hash_computation(self) -> None:
        with tempfile.NamedTemporaryFile("w", delete=False, encoding="utf-8") as f:
            f.write("hello world")
            tmp_path = Path(f.name)

        try:
            h = compute_file_hash(tmp_path)
            self.assertTrue(len(h) == 64)  # SHA-256 hex length
        finally:
            tmp_path.unlink()

    def test_recipe_creation_and_explain_up_to_date(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            dir_path = Path(tmp_dir)
            input_file = dir_path / "input.txt"
            output_file = dir_path / "output.txt"

            input_file.write_text("input data", encoding="utf-8")
            output_file.write_text("output result", encoding="utf-8")

            recipe = create_recipe(
                artifact_path=output_file,
                command="cat input.txt > output.txt",
                input_paths=[input_file],
            )

            recipe_file = get_recipe_path_for_artifact(output_file)
            save_recipe(recipe, recipe_file)

            explanation = explain_artifact(recipe_file)
            self.assertEqual(explanation["status"], "UP_TO_DATE")

    def test_explain_stale_input(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            dir_path = Path(tmp_dir)
            input_file = dir_path / "input.txt"
            output_file = dir_path / "output.txt"

            input_file.write_text("initial input", encoding="utf-8")
            output_file.write_text("processed output", encoding="utf-8")

            recipe = create_recipe(
                artifact_path=output_file,
                command="process input.txt output.txt",
                input_paths=[input_file],
            )

            recipe_file = get_recipe_path_for_artifact(output_file)
            save_recipe(recipe, recipe_file)

            # Modify input file to trigger staleness
            input_file.write_text("modified input data", encoding="utf-8")

            explanation = explain_artifact(recipe_file)
            self.assertEqual(explanation["status"], "STALE_INPUT_CHANGED")
            self.assertIn(str(input_file.resolve()), explanation["changed_inputs"])


if __name__ == "__main__":
    unittest.main()
