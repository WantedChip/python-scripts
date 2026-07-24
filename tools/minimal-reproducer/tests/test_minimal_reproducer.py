"""Unit tests for minimal_reproducer."""

import json
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

# noqa: E402
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import pytest  # noqa: E402
from minimal_reproducer.main import (  # noqa: E402
    evaluate_predicate,
    main,
    reduce_csv,
    reduce_json_object,
    reduce_lines_ddmin,
    render_text_report,
    shrink_minimal_reproducer,
)


def test_evaluate_predicate_mock() -> None:
    """Test evaluate_predicate with mock evaluator."""

    def mock_evaluator(content: str) -> bool:
        return "BUG" in content

    assert (
        evaluate_predicate("THIS HAS BUG IN IT", ".txt", "cmd", mock_evaluator) is True
    )
    assert evaluate_predicate("CLEAN CONTENT", ".txt", "cmd", mock_evaluator) is False


def test_evaluate_predicate_subprocess() -> None:
    """Test evaluate_predicate with subprocess run."""
    with patch("shutil.which", return_value="/usr/bin/python"):
        with patch("subprocess.run") as mock_run:
            mock_run.return_value.returncode = (
                1  # Non-zero returncode means failure reproduced
            )
            assert evaluate_predicate("test", ".txt", "python {file}") is True


def test_evaluate_predicate_error() -> None:
    """Test evaluate_predicate with subprocess exception."""
    with patch("shutil.which", return_value="/usr/bin/python"):
        with patch("subprocess.run", side_effect=Exception("Failed run")):
            assert evaluate_predicate("test", ".txt", "python {file}") is False


def test_reduce_lines_ddmin() -> None:
    """Test line reduction using ddmin algorithm."""
    lines = ["line1", "line2", "BUG_LINE", "line4", "line5"]

    def mock_evaluator(content: str) -> bool:
        return "BUG_LINE" in content

    reduced = reduce_lines_ddmin(lines, ".txt", "cmd", mock_evaluator)
    assert len(reduced) == 1
    assert reduced[0] == "BUG_LINE"


def test_reduce_json_object() -> None:
    """Test reducing JSON dict and list structures."""
    data = {
        "ok_key": 123,
        "bug_key": "TRIGGER_BUG",
        "nested": {"sub": "ok", "sub_bug": "TRIGGER_BUG"},
        "arr": [1, 2, "TRIGGER_BUG", 4],
    }

    def mock_evaluator(content: str) -> bool:
        return "TRIGGER_BUG" in content

    reduced = reduce_json_object(data, ".json", "cmd", mock_evaluator)
    assert "TRIGGER_BUG" in json.dumps(reduced)
    assert "ok_key" not in reduced


def test_reduce_csv() -> None:
    """Test reducing CSV rows while keeping headers."""
    csv_data = "col1,col2\n1,a\n2,TRIGGER_BUG\n3,c"

    def mock_evaluator(content: str) -> bool:
        return "TRIGGER_BUG" in content

    reduced = reduce_csv(csv_data, ".csv", "cmd", mock_evaluator)
    assert "col1,col2" in reduced
    assert "2,TRIGGER_BUG" in reduced
    assert "1,a" not in reduced


def test_shrink_minimal_reproducer_file_not_found() -> None:
    """Test error when input file does not exist."""
    with pytest.raises(FileNotFoundError):
        shrink_minimal_reproducer("/nonexistent/file.txt")


def test_shrink_minimal_reproducer_no_initial_failure() -> None:
    """Test error when initial input file does not reproduce failure."""
    with tempfile.NamedTemporaryFile("w", delete=False, suffix=".txt") as tmp:
        tmp.write("CLEAN")
        tmp_path = tmp.name

    def mock_evaluator(content: str) -> bool:
        return "BUG" in content

    with pytest.raises(RuntimeError, match="Initial input file did NOT trigger"):
        shrink_minimal_reproducer(tmp_path, mock_evaluator=mock_evaluator)


def test_shrink_minimal_reproducer_success() -> None:
    """Test successful reduction of a failing text file."""
    with tempfile.NamedTemporaryFile("w", delete=False, suffix=".txt") as tmp:
        tmp.write("line1\nline2\nBUG\nline4\n")
        tmp_path = tmp.name

    def mock_evaluator(content: str) -> bool:
        return "BUG" in content

    report = shrink_minimal_reproducer(tmp_path, mock_evaluator=mock_evaluator)

    assert report["reduction_percentage"] > 0
    assert "BUG" in report["minimal_content"]
    assert Path(report["output_file"]).is_file()


def test_render_text_report() -> None:
    """Test rendering text report."""
    report = {
        "input_file": "bug.json",
        "output_file": "bug.json.min",
        "file_type_used": "json",
        "initial_size_bytes": 100,
        "final_size_bytes": 10,
        "reduction_percentage": 90.0,
        "minimal_content": '{"bug": true}',
    }
    out = render_text_report(report)
    assert "Minimal Reproducer Reduction Report" in out
    assert "90.0%" in out


def test_cli_main_text(capsys: pytest.CaptureFixture[str]) -> None:
    """Test CLI main text output mode."""
    with patch(
        "sys.argv",
        [
            "minimal-reproducer",
            "--input",
            "bug.txt",
            "--command",
            "python test.py {file}",
        ],
    ):
        with patch("minimal_reproducer.main.shrink_minimal_reproducer") as mock_shrink:
            mock_shrink.return_value = {
                "input_file": "bug.txt",
                "output_file": "bug.txt.min",
                "file_type_used": "text",
                "initial_size_bytes": 50,
                "final_size_bytes": 10,
                "reduction_percentage": 80.0,
                "minimal_content": "BUG",
            }
            main()
            captured = capsys.readouterr()
            assert "Minimal Reproducer Reduction Report" in captured.out


def test_cli_main_json(capsys: pytest.CaptureFixture[str]) -> None:
    """Test CLI main json output mode."""
    with patch(
        "sys.argv",
        [
            "minimal-reproducer",
            "--input",
            "bug.txt",
            "--command",
            "cmd {file}",
            "--format",
            "json",
            "-v",
        ],
    ):
        with patch("minimal_reproducer.main.shrink_minimal_reproducer") as mock_shrink:
            mock_shrink.return_value = {"status": "ok"}
            main()
            captured = capsys.readouterr()
            parsed = json.loads(captured.out)
            assert parsed["status"] == "ok"


def test_cli_main_error() -> None:
    """Test CLI main exiting with code 1 on exception."""
    with patch(
        "sys.argv",
        ["minimal-reproducer", "--input", "invalid", "--command", "cmd {file}"],
    ):
        with patch(
            "minimal_reproducer.main.shrink_minimal_reproducer",
            side_effect=RuntimeError("Test error"),
        ):
            with pytest.raises(SystemExit) as exc:
                main()
            assert exc.value.code == 1
