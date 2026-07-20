"""Unit tests for license_reality_check.py."""

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, mock_open, patch

import pytest

# Add import injection to resolve checkers package
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# pylint: disable=import-error, wrong-import-position
import license_reality_check  # noqa: E402


def test_parse_requirements_txt(tmp_path: Path) -> None:
    """Test parse_requirements_txt with various format lines."""
    req_file = tmp_path / "requirements.txt"
    content = """
# This is a comment
-r other_reqs.txt
requests==2.28.1
numpy>=1.22.0
pytest<=7.0
pandas~=1.4.0
scipy!=1.8.0
scikit-learn
git+https://github.com/some/repo.git
./local_package
django@https://github.com/django/django/archive/master.tar.gz
"""
    req_file.write_text(content, encoding="utf-8")

    packages = license_reality_check.parse_requirements_txt(str(req_file))

    # Check that standard packages are extracted and local/git ones are ignored
    assert packages == [
        "requests",
        "numpy",
        "pytest",
        "pandas",
        "scipy",
        "scikit-learn",
    ]


def test_parse_requirements_txt_missing_and_error() -> None:
    """Test missing file and OS error handling in parse_requirements_txt."""
    # Non-existent file
    assert license_reality_check.parse_requirements_txt("non_existent_file.txt") == []

    # File that triggers OSError on open
    with patch("builtins.open", mock_open()) as mock_file:
        mock_file.side_effect = OSError("Permission denied")
        assert license_reality_check.parse_requirements_txt("some_file.txt") == []


@patch("urllib.request.urlopen")
def test_query_pypi_license_success(mock_urlopen: MagicMock) -> None:
    """Test query_pypi_license retrieves license and homepage successfully from PyPI."""
    # Mock successful response returning json data
    mock_response = MagicMock()
    mock_response.read.return_value = json.dumps(
        {
            "info": {
                "license": "MIT License",
                "home_page": "https://github.com/psf/requests",
                "classifiers": [
                    "Programming Language :: Python",
                    "License :: OSI Approved :: MIT License",
                ],
            }
        }
    ).encode("utf-8")
    mock_response.__enter__.return_value = mock_response
    mock_urlopen.return_value = mock_response

    lic, homepage = license_reality_check.query_pypi_license("requests")
    assert lic == "MIT License"
    assert homepage == "https://github.com/psf/requests"


@patch("urllib.request.urlopen")
def test_query_pypi_license_classifier_fallback(mock_urlopen: MagicMock) -> None:
    """Test query_pypi_license falls back to classifiers when license is empty."""
    # Case 1: license field is generic/empty
    mock_response = MagicMock()
    mock_response.read.return_value = json.dumps(
        {
            "info": {
                "license": "UNKNOWN",
                "home_page": "https://example.com",
                "classifiers": ["License :: OSI Approved :: Apache Software License"],
            }
        }
    ).encode("utf-8")
    mock_response.__enter__.return_value = mock_response
    mock_urlopen.return_value = mock_response

    lic, homepage = license_reality_check.query_pypi_license("some_package")
    assert lic == "Apache Software License"

    # Case 2: license field is too long
    long_desc = "A very long license description that exceeds 100 characters limit " * 3
    mock_response.read.return_value = json.dumps(
        {
            "info": {
                "license": long_desc,
                "home_page": "https://example.com",
                "classifiers": ["License :: OSI Approved :: BSD License"],
            }
        }
    ).encode("utf-8")

    lic, homepage = license_reality_check.query_pypi_license("some_package")
    assert lic == "BSD License"


@patch("urllib.request.urlopen")
def test_query_pypi_license_exception(mock_urlopen: MagicMock) -> None:
    """Test query_pypi_license returns Unknown on HTTP errors or exceptions."""
    mock_urlopen.side_effect = Exception("HTTP 404 Not Found")

    lic, homepage = license_reality_check.query_pypi_license("invalid-pkg-name")
    assert lic == "Unknown"
    assert homepage == ""


def test_evaluate_license_risk() -> None:
    """Test evaluate_license_risk correctly classifies risks."""
    # Permissive licenses
    assert license_reality_check.evaluate_license_risk("MIT") == (
        "Permissive",
        "Permissive open-source license. Safe to distribute.",
    )
    assert license_reality_check.evaluate_license_risk("Apache 2.0") == (
        "Permissive",
        "Permissive open-source license. Safe to distribute.",
    )
    assert license_reality_check.evaluate_license_risk("BSD-3-Clause") == (
        "Permissive",
        "Permissive open-source license. Safe to distribute.",
    )

    # Restrictive/Copyleft licenses
    assert license_reality_check.evaluate_license_risk("GPLv3") == (
        "High Risk",
        "Restrictive copyleft license (GPLv3). May require code disclosure.",
    )
    mpl_msg = (
        "Restrictive copyleft license (Mozilla Public License 2.0 (MPL 2.0)). "
        "May require code disclosure."
    )
    assert license_reality_check.evaluate_license_risk(
        "Mozilla Public License 2.0 (MPL 2.0)"
    ) == (
        "High Risk",
        mpl_msg,
    )

    # Missing license info
    assert license_reality_check.evaluate_license_risk("Unknown") == (
        "Warning",
        "License details not found on PyPI",
    )

    # Needs Review / Unclassified
    assert license_reality_check.evaluate_license_risk("Custom-Proprietary") == (
        "Needs Review",
        "Unclassified custom or hybrid license. Verify compatibility.",
    )


def test_main_missing_requirements_file() -> None:
    """Test main exits with 1 when requirements file is missing."""
    args = ["license_reality_check.py", "non_existent_file.txt"]
    with patch("sys.argv", args):
        with pytest.raises(SystemExit) as exc:
            license_reality_check.main()
        assert exc.value.code == 1


def test_main_empty_requirements_file(tmp_path: Path) -> None:
    """Test main exits with 0 and prints no packages message for empty requirements."""
    req_file = tmp_path / "requirements.txt"
    req_file.write_text("", encoding="utf-8")

    args = ["license_reality_check.py", str(req_file)]
    with patch("sys.argv", args):
        with pytest.raises(SystemExit) as exc:
            license_reality_check.main()
        assert exc.value.code == 0


@patch("license_reality_check.query_pypi_license")
def test_main_audit_run(
    mock_query: MagicMock, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Test main audits dependencies and displays results."""
    req_file = tmp_path / "requirements.txt"
    req_file.write_text("pkg-a\npkg-b\npkg-c\npkg-d\n", encoding="utf-8")

    # Mock PyPI lookups
    def query_mock(pkg_name: str):
        mapping = {
            "pkg-a": ("MIT", "http://a.com"),
            "pkg-b": ("GPLv3", "http://b.com"),
            "pkg-c": ("Unknown", ""),
            "pkg-d": ("Proprietary-Custom", "http://d.com"),
        }
        return mapping[pkg_name]

    mock_query.side_effect = query_mock

    args = ["license_reality_check.py", str(req_file)]
    with patch("sys.argv", args):
        license_reality_check.main()

    captured = capsys.readouterr().out

    # Verify outputs table structure
    assert "pkg-a" in captured
    assert "pkg-b" in captured
    assert "pkg-c" in captured
    assert "pkg-d" in captured
    assert "Permissive" in captured
    assert "High Risk" in captured
    assert "Warning" in captured
    assert "Needs Review" in captured

    # Verify counts in summary
    assert "Permissive Licenses: 1" in captured
    assert "Restrictive Copyleft: 1" in captured
    assert "Unclassified (Review): 1" in captured
    assert "Missing License:     1" in captured
