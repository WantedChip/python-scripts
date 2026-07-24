"""Unit tests for dependency_change_impact."""

import json
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

# noqa: E402
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import pytest  # noqa: E402
from dependency_change_impact.main import (  # noqa: E402
    DependencyImpactVisitor,
    analyze_dependency_change_impact,
    load_deprecated_rules,
    main,
    render_text_report,
    scan_impacted_codebase,
)


def test_dependency_impact_visitor() -> None:
    """Test AST DependencyImpactVisitor on imports, attributes, and symbols."""
    import ast

    code = (
        "import targetpkg as tp\n"
        "from targetpkg import BaseSettings, NormalSym\n"
        "tp.OldAttribute\n"
        "inst = BaseSettings()\n"
    )
    tree = ast.parse(code)
    visitor = DependencyImpactVisitor(
        target_package="targetpkg",
        deprecated_apis={"BaseSettings", "OldAttribute"},
        file_path="app.py",
    )
    visitor.visit(tree)

    assert len(visitor.impacts) >= 4
    high_risks = [imp for imp in visitor.impacts if imp.risk_level == "HIGH"]
    assert len(high_risks) >= 2


def test_load_deprecated_rules_list() -> None:
    """Test loading deprecated APIs from JSON array file."""
    with tempfile.NamedTemporaryFile("w", delete=False, suffix=".json") as tmp:
        tmp.write(json.dumps(["OldClass", "bad_func"]))
        tmp_path = tmp.name

    rules = load_deprecated_rules(tmp_path)
    assert "OldClass" in rules
    assert "bad_func" in rules


def test_load_deprecated_rules_dict() -> None:
    """Test loading deprecated APIs from JSON object file."""
    with tempfile.NamedTemporaryFile("w", delete=False, suffix=".json") as tmp:
        tmp.write(json.dumps({"deprecated_apis": ["OldClass"]}))
        tmp_path = tmp.name

    rules = load_deprecated_rules(tmp_path)
    assert "OldClass" in rules


def test_load_deprecated_rules_invalid() -> None:
    """Test loading deprecated APIs from nonexistent or invalid file."""
    assert load_deprecated_rules(None) == set()
    assert load_deprecated_rules("/nonexistent/file.json") == set()


def test_scan_impacted_codebase() -> None:
    """Test scanning a temporary codebase directory for impacted sites."""
    with tempfile.TemporaryDirectory() as tmpdir:
        file1 = Path(tmpdir) / "app.py"
        file1.write_text("import targetpkg\n", encoding="utf-8")

        bad_file = Path(tmpdir) / "invalid.py"
        bad_file.write_text("def broken(:", encoding="utf-8")

        impacts = scan_impacted_codebase(
            project_root=tmpdir,
            target_package="targetpkg",
            deprecated_apis=set(),
        )
        assert len(impacts) == 1
        assert impacts[0].file_path == "app.py"


def test_analyze_dependency_change_impact() -> None:
    """Test full dependency change impact analysis."""
    with tempfile.TemporaryDirectory() as tmpdir:
        file1 = Path(tmpdir) / "main.py"
        file1.write_text("from targetpkg import DeprecatedApi\n", encoding="utf-8")

        res = analyze_dependency_change_impact(
            target_package="targetpkg",
            project_root=tmpdir,
            deprecated_apis={"DeprecatedApi"},
        )
        assert res["total_impact_sites"] == 1
        assert res["risk_breakdown"]["HIGH"] == 1


def test_render_text_report() -> None:
    """Test text report formatting."""
    report = {
        "target_package": "pydantic",
        "project_root": "/project",
        "total_impact_sites": 1,
        "risk_breakdown": {"HIGH": 1, "MEDIUM": 0, "LOW": 0},
        "impacts": [
            {
                "file_path": "config.py",
                "line_number": 10,
                "expression": "from pydantic import BaseSettings",
                "risk_level": "HIGH",
                "reason": "Deprecated API",
            }
        ],
    }
    out = render_text_report(report)
    assert "pydantic" in out
    assert "HIGH=1" in out
    assert "config.py:10" in out


def test_cli_main_text(capsys: pytest.CaptureFixture[str]) -> None:
    """Test CLI main text output."""
    with patch("sys.argv", ["dependency-change-impact", "--package", "requests"]):
        with patch(
            "dependency_change_impact.main.analyze_dependency_change_impact"
        ) as mock_analyze:
            mock_analyze.return_value = {
                "target_package": "requests",
                "project_root": ".",
                "total_impact_sites": 0,
                "risk_breakdown": {"HIGH": 0, "MEDIUM": 0, "LOW": 0},
                "impacts": [],
            }
            main()
            captured = capsys.readouterr()
            assert "Dependency Change Impact Report" in captured.out


def test_cli_main_json(capsys: pytest.CaptureFixture[str]) -> None:
    """Test CLI main json output."""
    with patch(
        "sys.argv",
        [
            "dependency-change-impact",
            "--package",
            "requests",
            "--format",
            "json",
            "-v",
        ],
    ):
        with patch(
            "dependency_change_impact.main.analyze_dependency_change_impact"
        ) as mock_analyze:
            mock_analyze.return_value = {"status": "ok"}
            main()
            captured = capsys.readouterr()
            parsed = json.loads(captured.out)
            assert parsed["status"] == "ok"


def test_cli_main_error() -> None:
    """Test CLI main exiting with code 1 on exception."""
    with patch("sys.argv", ["dependency-change-impact", "--package", "invalid"]):
        with patch(
            "dependency_change_impact.main.analyze_dependency_change_impact",
            side_effect=RuntimeError("Test error"),
        ):
            with pytest.raises(SystemExit) as exc:
                main()
            assert exc.value.code == 1
