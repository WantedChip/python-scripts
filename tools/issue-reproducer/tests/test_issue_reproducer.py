"""Unit tests for issue-reproducer utility."""

import json
import os
import sys
import tempfile
import zipfile
from unittest.mock import MagicMock, patch

import pytest

# Insert parent dir to PATH to support folder-based import
sys.path.insert(0, "tools/issue-reproducer")

# pylint: disable=import-error,wrong-import-position
from issue_reproducer import (  # noqa: E402
    IssueReproducer,
    generate_reproduction_readme,
    get_venv_paths,
    main,
)


def test_get_venv_paths() -> None:
    """Test venv binary path resolution based on platforms."""
    python_p, pip_p = get_venv_paths("work")
    if sys.platform == "win32":
        assert python_p == os.path.join("work", ".venv", "Scripts", "python.exe")
        assert pip_p == os.path.join("work", ".venv", "Scripts", "pip.exe")
    else:
        assert python_p == os.path.join("work", ".venv", "bin", "python")
        assert pip_p == os.path.join("work", ".venv", "bin", "pip")


def test_generate_reproduction_readme() -> None:
    """Test generating a markdown readme report."""
    readme = generate_reproduction_readme(
        "python script.py", 1, 1, True, False, False, 1.25
    )
    assert "# Issue Reproduction Workspace" in readme
    assert "**Reproduced Status**: `REPRODUCED`" in readme
    assert "**Original Exit Code**: `1`" in readme
    assert "**Reproduction Exit Code**: `1`" in readme


def test_issue_reproducer_flow() -> None:
    """Test full reproducer pipeline by mocking zipfile and subprocess execution."""
    with tempfile.TemporaryDirectory() as temp_dir:
        # Create a mock bundle zip
        bundle_zip = os.path.join(temp_dir, "test_bundle.zip")
        manifest = {
            "exit_code": 1,
            "command": "python script.py",
            "packages": {"requests": "2.28.0"},
        }
        with zipfile.ZipFile(bundle_zip, "w") as zf:
            zf.writestr("manifest.json", json.dumps(manifest))
            zf.writestr("stdout.log", "Original stdout")
            zf.writestr("stderr.log", "Original stderr")

        repro_dir = os.path.join(temp_dir, "workspace")
        reproducer = IssueReproducer(bundle_zip, repro_dir)

        workspace_path = reproducer.setup_workspace()
        assert workspace_path == repro_dir
        assert os.path.exists(os.path.join(repro_dir, "manifest.json"))

        # Mock target subprocess runs for creating venv,
        # installing package, and executing
        with patch("subprocess.run") as mock_run:
            mock_res = MagicMock()
            mock_res.returncode = 1
            mock_res.stdout = "Reproduced stdout"
            mock_res.stderr = "Reproduced stderr"
            mock_run.return_value = mock_res

            report = reproducer.run_reproduction(workspace_path)

            assert report["reproduced"] is True
            assert report["original_exit_code"] == 1
            assert report["reproduction_exit_code"] == 1
            assert report["stdout_differs"] is True
            assert report["stderr_differs"] is True

            # Verify files written
            assert os.path.exists(os.path.join(repro_dir, "reproduction_stdout.log"))
            assert os.path.exists(os.path.join(repro_dir, "reproduction_stderr.log"))
            assert os.path.exists(os.path.join(repro_dir, "reproduction_readme.md"))
            assert os.path.exists(os.path.join(repro_dir, "reproduction_report.json"))


@patch("issue_reproducer.IssueReproducer.setup_workspace")
@patch("issue_reproducer.IssueReproducer.run_reproduction")
def test_main_cli(
    mock_run: MagicMock, mock_setup: MagicMock, capsys: pytest.CaptureFixture[str]
) -> None:
    """Test CLI arguments and execution main thread."""
    mock_setup.return_value = "/tmp/workspace"
    mock_run.return_value = {
        "reproduced": True,
        "original_exit_code": 1,
        "reproduction_exit_code": 1,
        "reproduction_duration_seconds": 0.5,
    }

    with patch("sys.argv", ["issue-reproducer", "-b", "bundle.zip", "--keep"]):
        main()
        captured = capsys.readouterr()
        assert "Workspace initialized:" in captured.out
        assert "Reproduced: True" in captured.out
