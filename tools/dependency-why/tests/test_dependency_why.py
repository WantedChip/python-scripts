"""Unit tests for dependency_why."""

import json
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

# noqa: E402
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import pytest  # noqa: E402
from dependency_why.main import (  # noqa: E402
    ImportVisitor,
    analyze_dependency_why,
    find_dependency_chains,
    get_all_installed_packages,
    main,
    render_text_report,
    scan_codebase_imports,
)


def test_get_all_installed_packages() -> None:
    """Test retrieving installed package dependency map."""
    mock_dist = MagicMock()
    mock_dist.metadata = {"Name": "Requests"}

    with patch("dependency_why.main.distributions", return_value=[mock_dist]):
        with patch(
            "dependency_why.main.requires",
            return_value=['urllib3 (>=1.21.1); extra == "socks"'],
        ):
            pkgs = get_all_installed_packages()
            assert "requests" in pkgs
            assert "urllib3" in pkgs["requests"]


def test_find_dependency_chains() -> None:
    """Test finding dependency chains for target package."""
    pkg_deps = {
        "foo": {"bar", "baz"},
        "bar": {"target_pkg"},
        "target_pkg": set(),
    }
    chains = find_dependency_chains("target_pkg", pkg_deps)
    assert len(chains) == 1
    assert chains[0] == ["bar", "target_pkg"]


def test_import_visitor() -> None:
    """Test AST ImportVisitor node handling."""
    import ast

    code = "import mypkg\nfrom mypkg.sub import func\nimport otherpkg"
    tree = ast.parse(code)
    visitor = ImportVisitor("mypkg")
    visitor.visit(tree)

    assert len(visitor.found_imports) == 2
    assert visitor.found_imports[0] == (1, "mypkg")
    assert visitor.found_imports[1] == (2, "mypkg.sub")


def test_scan_codebase_imports() -> None:
    """Test scanning a temporary directory for python file imports."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        file1 = tmp_path / "app.py"
        file1.write_text("import targetpkg\n", encoding="utf-8")

        file2 = tmp_path / "utils.py"
        file2.write_text("import sys\n", encoding="utf-8")

        bad_file = tmp_path / "broken.py"
        bad_file.write_text("def invalid_syntax(:", encoding="utf-8")

        res = scan_codebase_imports(tmpdir, "targetpkg")
        assert "app.py" in res
        assert res["app.py"][0] == (1, "targetpkg")
        assert "utils.py" not in res


def test_analyze_dependency_why_safe_to_remove() -> None:
    """Test analyze_dependency_why when package is safe to remove."""
    with tempfile.TemporaryDirectory() as tmpdir:
        mock_deps = {"otherpkg": set(), "targetpkg": set()}
        res = analyze_dependency_why(
            target_package="targetpkg",
            project_root=tmpdir,
            mock_pkg_deps=mock_deps,
        )
        assert res["is_installed"] is True
        assert res["imported_in_codebase"] is False
        assert "Safe to remove" in res["consequences_of_removal"][0]


def test_analyze_dependency_why_in_use() -> None:
    """Test analyze_dependency_why when package is imported and required."""
    with tempfile.TemporaryDirectory() as tmpdir:
        file1 = Path(tmpdir) / "main.py"
        file1.write_text("import targetpkg\n", encoding="utf-8")

        mock_deps = {"parentpkg": {"targetpkg"}}
        res = analyze_dependency_why(
            target_package="targetpkg",
            project_root=tmpdir,
            mock_pkg_deps=mock_deps,
        )
        assert res["imported_in_codebase"] is True
        assert len(res["dependency_chains"]) == 1
        assert len(res["consequences_of_removal"]) == 2


def test_render_text_report() -> None:
    """Test rendering text report."""
    report = {
        "target_package": "requests",
        "is_installed": True,
        "dependency_chains": [["pip", "requests"]],
        "code_usage_summary": {"main.py": [(5, "requests")]},
        "consequences_of_removal": ["Codebase breakage"],
    }
    out = render_text_report(report)
    assert "requests" in out
    assert "pip -> requests" in out
    assert "File: main.py" in out


def test_cli_main_text(capsys: pytest.CaptureFixture[str]) -> None:
    """Test CLI main text output mode."""
    with patch("sys.argv", ["dependency-why", "--package", "requests"]):
        with patch("dependency_why.main.analyze_dependency_why") as mock_analyze:
            mock_analyze.return_value = {
                "target_package": "requests",
                "is_installed": True,
                "dependency_chains": [],
                "code_usage_summary": {},
                "consequences_of_removal": [],
            }
            main()
            captured = capsys.readouterr()
            assert "Dependency Why Report" in captured.out


def test_cli_main_json(capsys: pytest.CaptureFixture[str]) -> None:
    """Test CLI main json output mode."""
    with patch(
        "sys.argv",
        ["dependency-why", "--package", "requests", "--format", "json", "-v"],
    ):
        with patch("dependency_why.main.analyze_dependency_why") as mock_analyze:
            mock_analyze.return_value = {"status": "ok"}
            main()
            captured = capsys.readouterr()
            parsed = json.loads(captured.out)
            assert parsed["status"] == "ok"


def test_cli_main_error() -> None:
    """Test CLI main exiting with code 1 on exception."""
    with patch("sys.argv", ["dependency-why", "--package", "invalid"]):
        with patch(
            "dependency_why.main.analyze_dependency_why",
            side_effect=RuntimeError("Test error"),
        ):
            with pytest.raises(SystemExit) as exc:
                main()
            assert exc.value.code == 1
