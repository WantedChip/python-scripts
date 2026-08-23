"""Unit tests for artifact-recipe main.py."""

import contextlib
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from typing import Any, Dict, List, Tuple
from unittest.mock import patch

from main import (
    collect_env_vars,
    compute_file_hash,
    create_recipe,
    explain_artifact,
    get_recipe_path_for_artifact,
    load_recipe,
    main,
    save_recipe,
)


def _make_recorded_artifact(dir_path: Path, stem: str) -> Tuple[Path, Path]:
    """Creates input+artifact files and records a sidecar recipe for them."""
    input_file = dir_path / f"{stem}_input.txt"
    artifact = dir_path / f"{stem}.txt"
    input_file.write_text("input data", encoding="utf-8")
    artifact.write_text("output result", encoding="utf-8")
    recipe = create_recipe(
        artifact_path=artifact,
        command=f"build {stem}",
        input_paths=[input_file],
    )
    recipe_file = get_recipe_path_for_artifact(artifact)
    save_recipe(recipe, recipe_file)
    return artifact, recipe_file


def _run_cli(args: List[str]) -> Any:
    """Runs the CLI entrypoint capturing stdout/stderr; returns (code, out, err)."""
    out_buf, err_buf = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out_buf), contextlib.redirect_stderr(err_buf):
        code = main(args)
    return code, out_buf.getvalue(), err_buf.getvalue()


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


class TestHashAndEnvHelpers(unittest.TestCase):
    """Tests for hashing and environment-variable helper edge cases."""

    def test_hash_missing_file_returns_empty_string(self) -> None:
        missing = Path(tempfile.gettempdir()) / "no_such_file_12345.bin"
        self.assertEqual(compute_file_hash(missing), "")

    def test_collect_env_vars_without_names_returns_empty_dict(self) -> None:
        self.assertEqual(collect_env_vars(None), {})
        self.assertEqual(collect_env_vars([]), {})

    def test_collect_env_vars_reads_environment(self) -> None:
        with patch.dict(os.environ, {"AR_PRESENT_VAR": "value42", "AR_GONE_VAR": ""}):
            del os.environ["AR_GONE_VAR"]
            collected = collect_env_vars(["AR_PRESENT_VAR", "AR_GONE_VAR"])
        self.assertEqual(collected["AR_PRESENT_VAR"], "value42")
        self.assertEqual(collected["AR_GONE_VAR"], "")

    def test_create_recipe_records_missing_input_with_zero_meta(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            dir_path = Path(tmp_dir)
            ghost_input = dir_path / "ghost.txt"
            artifact = dir_path / "out.txt"
            artifact.write_text("data", encoding="utf-8")
            recipe = create_recipe(
                artifact_path=artifact,
                command="gen",
                input_paths=[ghost_input],
            )
            record = recipe["inputs"][0]
            self.assertEqual(record["mtime"], 0)
            self.assertEqual(record["size_bytes"], 0)
            self.assertEqual(record["sha256"], "")

    def test_load_recipe_returns_empty_dict_for_non_mapping_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / "bad.recipe.json"
            path.write_text("[1, 2, 3]", encoding="utf-8")
            self.assertEqual(load_recipe(path), {})


class TestExplainArtifactStatuses(unittest.TestCase):
    """Tests for each staleness status reported by explain_artifact."""

    def test_missing_artifact_reported(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            artifact, recipe_file = _make_recorded_artifact(Path(tmp_dir), "gone")
            artifact.unlink()
            explanation = explain_artifact(recipe_file)
            self.assertEqual(explanation["status"], "ARTIFACT_MISSING")
            self.assertTrue(explanation["details"])
            self.assertIn("no longer exists", explanation["details"][0])

    def test_mutated_artifact_reported_with_hashes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            artifact, recipe_file = _make_recorded_artifact(Path(tmp_dir), "mut")
            artifact.write_text("tampered content", encoding="utf-8")
            explanation = explain_artifact(recipe_file)
            self.assertEqual(explanation["status"], "ARTIFACT_MUTATED")
            self.assertIn("out-of-band", explanation["details"][0])

    def test_missing_input_takes_priority_over_changed_status(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            dir_path = Path(tmp_dir)
            _, recipe_file = _make_recorded_artifact(dir_path, "miss")
            recipe = load_recipe(recipe_file)
            inp = Path(recipe["inputs"][0]["path"])
            other_input = dir_path / "second_input.txt"
            other_input.write_text("more data", encoding="utf-8")
            # Re-record so the recipe has two inputs, then delete both.
            artifact = Path(recipe["artifact"]["path"])
            fresh = create_recipe(
                artifact_path=artifact,
                command="build",
                input_paths=[inp, other_input],
            )
            save_recipe(fresh, recipe_file)
            inp.unlink()
            other_input.unlink()
            explanation = explain_artifact(recipe_file)
            self.assertEqual(explanation["status"], "STALE_MISSING_INPUT")
            self.assertIn(str(inp), explanation["missing_inputs"])
            self.assertIn(str(other_input.resolve()), explanation["missing_inputs"])


class TestRecordCommand(unittest.TestCase):
    """Tests for the ``record`` subcommand."""

    def test_record_writes_default_sidecar_and_captures_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            dir_path = Path(tmp_dir)
            input_file = dir_path / "in.txt"
            artifact = dir_path / "out.bin"
            input_file.write_text("raw", encoding="utf-8")
            artifact.write_text("built", encoding="utf-8")

            with patch.dict(os.environ, {"AR_TOKEN": "tok123"}):
                code, out, _ = _run_cli(
                    [
                        "record",
                        "--artifact",
                        str(artifact),
                        "--command",
                        "assemble in.txt",
                        "--inputs",
                        str(input_file),
                        "--env-vars",
                        "AR_TOKEN",
                    ]
                )

            self.assertEqual(code, 0)
            self.assertIn("Recorded provenance sidecar", out)
            sidecar = get_recipe_path_for_artifact(artifact)
            self.assertTrue(sidecar.exists())
            recipe = load_recipe(sidecar)
            self.assertEqual(recipe["provenance"]["command"], "assemble in.txt")
            self.assertEqual(
                recipe["provenance"]["environment_variables"]["AR_TOKEN"],
                "tok123",
            )
            self.assertEqual(
                recipe["inputs"][0]["sha256"], compute_file_hash(input_file)
            )

    def test_record_custom_output_path_is_honoured(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            dir_path = Path(tmp_dir)
            artifact = dir_path / "a.txt"
            artifact.write_text("x", encoding="utf-8")
            custom = dir_path / "custom" / "side.json"
            custom.parent.mkdir()
            code, _, _ = _run_cli(
                [
                    "record",
                    "-a",
                    str(artifact),
                    "-c",
                    "gen",
                    "--output",
                    str(custom),
                ]
            )
            self.assertEqual(code, 0)
            self.assertTrue(custom.exists())

    def test_record_run_executes_command_then_records(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            dir_path = Path(tmp_dir)
            artifact = dir_path / "r.txt"
            artifact.write_text("x", encoding="utf-8")
            with patch("main.subprocess.run") as mock_run:
                mock_run.return_value.returncode = 0
                code, out, _ = _run_cli(
                    ["record", "-a", str(artifact), "-c", "make r.txt", "--run"]
                )
            self.assertEqual(code, 0)
            mock_run.assert_called_once()
            self.assertIn("Executing command: make r.txt", out)
            self.assertIn("Recorded provenance sidecar", out)
            self.assertTrue(get_recipe_path_for_artifact(artifact).exists())

    def test_record_run_failure_propagates_exit_code_without_sidecar(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            dir_path = Path(tmp_dir)
            artifact = dir_path / "f.txt"
            artifact.write_text("x", encoding="utf-8")
            with patch("main.subprocess.run") as mock_run:
                mock_run.return_value.returncode = 7
                code, _, err = _run_cli(
                    ["record", "-a", str(artifact), "-c", "boom", "--run"]
                )
            self.assertEqual(code, 7)
            self.assertIn("exit code 7", err)
            self.assertFalse(get_recipe_path_for_artifact(artifact).exists())


class TestExplainCommand(unittest.TestCase):
    """Tests for the ``explain`` subcommand output formats."""

    def test_explain_missing_sidecar_returns_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            orphan = Path(tmp_dir) / "orphan.txt"
            orphan.write_text("no recipe here", encoding="utf-8")
            code, _, err = _run_cli(["explain", str(orphan)])
            self.assertEqual(code, 1)
            self.assertIn("does not exist", err)

    def test_explain_accepts_sidecar_path_directly_as_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            _, recipe_file = _make_recorded_artifact(Path(tmp_dir), "direct")
            code, out, _ = _run_cli(["explain", str(recipe_file), "--format", "json"])
            self.assertEqual(code, 0)
            parsed = json.loads(out)
            self.assertEqual(parsed["status"], "UP_TO_DATE")
            self.assertEqual(parsed["command"], "build direct")

    def test_explain_resolves_artifact_to_sidecar_in_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            artifact, recipe_file = _make_recorded_artifact(Path(tmp_dir), "res")
            self.assertNotEqual(artifact, recipe_file)
            code, out, _ = _run_cli(["explain", str(artifact), "--format", "json"])
            self.assertEqual(code, 0)
            self.assertEqual(json.loads(out)["artifact_path"], str(artifact.resolve()))

    def test_explain_text_up_to_date_prints_confirmation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            artifact, _ = _make_recorded_artifact(Path(tmp_dir), "ok")
            code, out, _ = _run_cli(["explain", str(artifact)])
            self.assertEqual(code, 0)
            self.assertIn("Status:      [UP_TO_DATE]", out)
            self.assertIn("fully UP TO DATE", out)

    def test_explain_text_lists_details_when_stale(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            artifact, _ = _make_recorded_artifact(Path(tmp_dir), "stale")
            artifact.write_text("changed bytes", encoding="utf-8")
            code, out, _ = _run_cli(["explain", str(artifact)])
            self.assertEqual(code, 0)
            self.assertIn("[ARTIFACT_MUTATED]", out)
            self.assertIn("Details:", out)
            self.assertIn("out-of-band", out)


class TestVerifyCommand(unittest.TestCase):
    """Tests for the ``verify`` subcommand directory sweep."""

    def test_verify_empty_directory_reports_nothing_found(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            code, out, _ = _run_cli(["verify", tmp_dir])
            self.assertEqual(code, 0)
            self.assertIn("No .recipe.json sidecar files found.", out)

    def test_verify_reports_ok_and_stale_and_fails_on_stale(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            dir_path = Path(tmp_dir)
            ok_artifact, _ = _make_recorded_artifact(dir_path, "good")
            bad_artifact, _ = _make_recorded_artifact(dir_path, "bad")
            bad_artifact.write_text("mutated!", encoding="utf-8")
            code, out, _ = _run_cli(["verify", tmp_dir])
            self.assertEqual(code, 1)
            self.assertIn(f"[OK] UP_TO_DATE: {ok_artifact.resolve()}", out)
            self.assertIn("[STALE] ARTIFACT_MUTATED", out)
            self.assertIn("Summary: 1 Up to date, 1 Stale/Mutated.", out)

    def test_verify_all_clean_exits_zero(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            _make_recorded_artifact(Path(tmp_dir), "clean")
            code, out, _ = _run_cli(["verify", tmp_dir])
            self.assertEqual(code, 0)
            self.assertIn("Summary: 1 Up to date, 0 Stale/Mutated.", out)

    def test_verify_json_format_emits_result_list(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            dir_path = Path(tmp_dir)
            _make_recorded_artifact(dir_path, "j1")
            j2, _ = _make_recorded_artifact(dir_path, "j2")
            j2.write_text("edited", encoding="utf-8")
            code, out, _ = _run_cli(["verify", tmp_dir, "--format", "json"])
            self.assertEqual(code, 0)
            results: List[Dict[str, Any]] = json.loads(out)
            statuses = sorted(r["status"] for r in results)
            self.assertEqual(statuses, ["ARTIFACT_MUTATED", "UP_TO_DATE"])

    def test_parser_requires_subcommand(self) -> None:
        with self.assertRaises(SystemExit):
            main([])


if __name__ == "__main__":
    unittest.main()
