"""Unit tests for Repository Documentation Auditor."""

import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

# Insert src directory to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from repository_documentation_auditor.main import (  # noqa: E402
    DocAuditor,
    main,
    slugify,
)


def test_slugify() -> None:
    """Test markdown heading to anchor slug conversion."""
    assert slugify("Installation Instruction") == "installation-instruction"
    assert slugify("Header @#$ Special!") == "header-special"
    assert slugify("  Multiple   Spaces  ") == "multiple-spaces"


@pytest.fixture
def mock_repo(tmp_path: Path) -> Path:
    """Creates a temporary repository structure for auditing tests."""
    # Write a basic README
    readme = tmp_path / "README.md"
    readme.write_text(
        "# My Project\n\n"
        "## Installation\n"
        "To install dependencies run:\n"
        "```bash\n"
        "pip install -r requirements.txt\n"
        "```\n\n"
        "Also see [Usage Guidance](#usage)\n"
        "And visit [Details Doc](docs/details.md)\n"
        "Or [Invalid File](docs/missing.md)\n"
        "Let's execute: `python scripts/hello.py`\n"
        "And dead script: `python scripts/dead.py`\n",
        encoding="utf-8",
    )

    # Requirements
    req = tmp_path / "requirements.txt"
    req.write_text("requests==2.31.0\n")

    # Script files
    scripts_dir = tmp_path / "scripts"
    scripts_dir.mkdir()
    hello_py = scripts_dir / "hello.py"
    hello_py.write_text(
        "import os\n"
        "val = os.getenv('DB_PASSWORD')\n"
        "port = os.environ.get('PORT')\n"
        "user = os.environ['DB_USER']\n"
    )

    # Documentation files
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    details_md = docs_dir / "details.md"
    details_md.write_text(
        "# Details Page\n"
        "See [Setup Instructions](../README.md#installation)\n"
        "Broken anchor [Link](#non-existent)\n"
    )

    return tmp_path


def test_audit_setup_instructions(mock_repo: Path) -> None:
    """Test setup instruction compliance audits."""
    auditor = DocAuditor(mock_repo, [])
    auditor.audit_setup_instructions()
    assert not any(issue["category"] == "setup" for issue in auditor.issues)

    # Break it by deleting requirements.txt mention
    readme = mock_repo / "README.md"
    readme.write_text(
        "# Project\n## Run\nNo installation header, no requirements",
        encoding="utf-8",
    )
    auditor2 = DocAuditor(mock_repo, [])
    auditor2.audit_setup_instructions()
    issues = [i for i in auditor2.issues if i["category"] == "setup"]
    assert len(issues) == 2  # Missing setup header & requirements.txt not mentioned


def test_audit_dead_commands(mock_repo: Path) -> None:
    """Test identification of non-existent script references."""
    auditor = DocAuditor(mock_repo, [])
    auditor.audit_dead_commands()
    issues = [i for i in auditor.issues if i["category"] == "dead_command"]
    assert len(issues) == 1
    assert "scripts/dead.py" in issues[0]["description"]


def test_audit_undocumented_env_vars(mock_repo: Path) -> None:
    """Test identification of undocumented env vars."""
    auditor = DocAuditor(mock_repo, [])
    auditor.audit_undocumented_env_vars()
    issues = [i for i in auditor.issues if i["category"] == "undocumented_env"]
    # DB_PASSWORD, PORT, DB_USER are used, but not documented in markdown/env.example
    assert len(issues) == 3
    vars_found = {i["description"].split("'")[1] for i in issues}
    assert vars_found == {"DB_PASSWORD", "PORT", "DB_USER"}


def test_audit_stale_references(mock_repo: Path) -> None:
    """Test markdown links and anchor audits."""
    auditor = DocAuditor(mock_repo, [])
    auditor.audit_stale_references()

    issues = auditor.issues
    categories = [i["category"] for i in issues]

    # Broken local link in README (docs/missing.md)
    assert "broken_path" in categories
    # Broken internal link in details.md (#non-existent)
    assert "stale_anchor" in categories

    # Valid link (docs/details.md) should NOT produce issues
    valid_details_issues = [
        i
        for i in issues
        if "details.md" in i["description"] and i["category"] == "broken_path"
    ]
    assert len(valid_details_issues) == 0


def test_cli_execution_json(mock_repo: Path) -> None:
    """Test auditor CLI JSON output."""
    test_args = ["repository_documentation_auditor", str(mock_repo), "--json"]

    with patch.object(sys, "argv", test_args), patch("sys.stdout.write") as mock_write:
        main()
        assert mock_write.called
        written_string = "".join(
            call.args[0] for call in mock_write.call_args_list if call.args
        )
        data = json.loads(written_string)
        categories = {issue["category"] for issue in data}
        assert "broken_path" in categories
        assert "dead_command" in categories


def test_cli_execution_text(mock_repo: Path, capsys) -> None:
    """Test auditor CLI standard terminal output."""
    test_args = ["repository_documentation_auditor", str(mock_repo)]
    with patch.object(sys, "argv", test_args):
        main()
    captured = capsys.readouterr()
    assert "Auditor detected" in captured.out
    assert "dead_command" in captured.out


def test_cli_fail_on_warnings(mock_repo: Path) -> None:
    """Test auditor exit code behavior with fail-on-warnings."""
    test_args = [
        "repository_documentation_auditor",
        str(mock_repo),
        "--fail-on-warnings",
    ]
    with patch.object(sys, "argv", test_args), pytest.raises(SystemExit) as exc:
        main()
    assert exc.value.code == 1


def test_cli_invalid_dir() -> None:
    """Test error code for non-existent target path."""
    test_args = ["repository_documentation_auditor", "/invalid/dir/path/nowhere"]
    with patch.object(sys, "argv", test_args), pytest.raises(SystemExit) as exc:
        main()
    assert exc.value.code == 2


def test_audit_undocumented_env_vars_success(mock_repo: Path) -> None:
    """Test documented env vars do not generate warnings."""
    # Write variables to readme
    readme = mock_repo / "README.md"
    readme.write_text(
        "# Project\n"
        "## Setup\n"
        "Requirements: DB_PASSWORD, PORT, DB_USER variables.",
        encoding="utf-8",
    )
    auditor = DocAuditor(mock_repo, [])
    auditor.audit_undocumented_env_vars()
    issues = [i for i in auditor.issues if i["category"] == "undocumented_env"]
    assert len(issues) == 0
