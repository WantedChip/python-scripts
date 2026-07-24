"""Unit tests for test_order_hunter."""

import json
import sys
import tempfile
from pathlib import Path
from typing import List, Tuple
from unittest.mock import patch

# noqa: E402
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import pytest  # noqa: E402
from test_order_hunter.main import (  # noqa: E402
    bisect_culprits,
    discover_test_files,
    hunt_test_order_dependencies,
    main,
    render_text_report,
    run_test_sequence,
)


def test_discover_test_files() -> None:
    """Test discovering test files in directory and single file."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        t1 = tmp_path / "test_one.py"
        t1.write_text("def test_a(): pass\n", encoding="utf-8")
        t2 = tmp_path / "two_test.py"
        t2.write_text("def test_b(): pass\n", encoding="utf-8")
        other = tmp_path / "helper.py"
        other.write_text("x = 1\n", encoding="utf-8")

        files = discover_test_files(tmpdir)
        assert len(files) == 2
        assert any("test_one.py" in f for f in files)
        assert any("two_test.py" in f for f in files)

        single_file = discover_test_files(str(t1))
        assert len(single_file) == 1


def test_run_test_sequence_empty() -> None:
    """Test running empty test sequence."""
    passed, out = run_test_sequence([])
    assert passed is True
    assert out == ""


def test_run_test_sequence_mocked_subprocess() -> None:
    """Test running test sequence with mocked subprocess."""
    with patch("shutil.which", return_value="/usr/bin/pytest"):
        with patch("subprocess.run") as mock_run:
            mock_run.return_value.returncode = 0
            mock_run.return_value.stdout = "OK"
            mock_run.return_value.stderr = ""

            passed, out = run_test_sequence(["test_a.py"])
            assert passed is True
            assert "OK" in out


def test_run_test_sequence_error() -> None:
    """Test running test sequence when process raises exception."""
    with patch("shutil.which", return_value="/usr/bin/pytest"):
        with patch("subprocess.run", side_effect=Exception("Execution fail")):
            passed, out = run_test_sequence(["test_a.py"])
            assert passed is False
            assert "Execution fail" in out


def test_bisect_culprits() -> None:
    """Test bisecting culprit tests that pollute state for victim."""

    def mock_runner(seq: List[str]) -> Tuple[bool, str]:
        # Fails if 'bad_test.py' is present before 'victim.py'
        if "bad_test.py" in seq and "victim.py" in seq:
            return False, "Polluted state failure"
        return True, "Passed"

    culprits = bisect_culprits(
        victim="victim.py",
        preceding_tests=["good1.py", "bad_test.py", "good2.py"],
        runner_func=mock_runner,
    )
    assert "bad_test.py" in culprits


def test_hunt_test_order_dependencies() -> None:
    """Test full test order hunting with simulated state pollution."""
    with tempfile.TemporaryDirectory() as tmpdir:
        t1 = Path(tmpdir) / "test_polluter.py"
        t1.write_text("def test_pollute(): pass\n", encoding="utf-8")
        t2 = Path(tmpdir) / "test_victim.py"
        t2.write_text("def test_victim(): pass\n", encoding="utf-8")

        def mock_runner(seq: List[str]) -> Tuple[bool, str]:
            if len(seq) == 1:
                return True, "Pass alone"
            if (
                len(seq) >= 2
                and any("polluter" in s for s in seq)
                and any("victim" in s for s in seq)
            ):
                p_idx = next(i for i, s in enumerate(seq) if "polluter" in s)
                v_idx = next(i for i, s in enumerate(seq) if "victim" in s)
                if p_idx < v_idx:
                    return False, "Order failure"
            return True, "Pass"

        res = hunt_test_order_dependencies(
            test_dir=tmpdir,
            iterations=5,
            seed=42,
            mock_runner=mock_runner,
        )
        assert res["tests_found"] == 2
        assert res["dependencies_found_count"] >= 1


def test_hunt_test_order_dependencies_no_files() -> None:
    """Test hunting when test directory contains no test files."""
    res = hunt_test_order_dependencies("/nonexistent_dir")
    assert res["tests_found"] == 0
    assert "error" in res


def test_render_text_report() -> None:
    """Test text report formatting."""
    report = {
        "test_dir": "/tests",
        "tests_found": 5,
        "isolated_passing_tests": 5,
        "iterations_run": 10,
        "dependencies_found_count": 1,
        "order_dependencies": [
            {
                "victim_test": "test_b.py",
                "culprit_tests": ["test_a.py"],
                "seed_used": 12345,
                "iteration": 2,
                "reproduce_command": "pytest test_a.py test_b.py",
            }
        ],
    }
    out = render_text_report(report)
    assert "Test Order Hunter Report" in out
    assert "test_b.py" in out
    assert "test_a.py" in out


def test_cli_main_text(capsys: pytest.CaptureFixture[str]) -> None:
    """Test CLI main text output mode."""
    with patch("sys.argv", ["test-order-hunter", "--test-dir", "."]):
        with patch("test_order_hunter.main.hunt_test_order_dependencies") as mock_hunt:
            mock_hunt.return_value = {
                "test_dir": ".",
                "tests_found": 1,
                "isolated_passing_tests": 1,
                "iterations_run": 1,
                "dependencies_found_count": 0,
                "order_dependencies": [],
            }
            main()
            captured = capsys.readouterr()
            assert "Test Order Hunter Report" in captured.out


def test_cli_main_json(capsys: pytest.CaptureFixture[str]) -> None:
    """Test CLI main json output mode."""
    with patch(
        "sys.argv",
        ["test-order-hunter", "--test-dir", ".", "--format", "json", "-v"],
    ):
        with patch("test_order_hunter.main.hunt_test_order_dependencies") as mock_hunt:
            mock_hunt.return_value = {"status": "ok"}
            main()
            captured = capsys.readouterr()
            parsed = json.loads(captured.out)
            assert parsed["status"] == "ok"


def test_cli_main_error() -> None:
    """Test CLI main exiting with code 1 on exception."""
    with patch("sys.argv", ["test-order-hunter", "--test-dir", "invalid"]):
        with patch(
            "test_order_hunter.main.hunt_test_order_dependencies",
            side_effect=RuntimeError("Test error"),
        ):
            with pytest.raises(SystemExit) as exc:
                main()
            assert exc.value.code == 1
