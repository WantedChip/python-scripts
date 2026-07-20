import sys
import urllib.error
from pathlib import Path
from unittest.mock import MagicMock, mock_open, patch

import pytest

# Add import injection to resolve dependency_risk_report
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# pylint: disable=import-error, wrong-import-position
import dependency_risk_report  # noqa: E402


# Test cases for parse_requirements_txt
def test_parse_requirements_txt_nonexistent():
    assert dependency_risk_report.parse_requirements_txt("nonexistent_file.txt") == []


def test_parse_requirements_txt_valid():
    file_content = """
    # This is a comment
    requests==2.28.1
    numpy>=1.22.0
    pandas<=1.5.0
    scipy~=1.9.0
    matplotlib!=3.5.0
    -r other-requirements.txt
    ./local-package
    flask
    """
    with patch("os.path.exists", return_value=True):
        with patch("builtins.open", mock_open(read_data=file_content)):
            packages = dependency_risk_report.parse_requirements_txt("requirements.txt")
            assert ("requests", "2.28.1") in packages
            assert ("numpy", "1.22.0") in packages
            assert ("pandas", "1.5.0") in packages
            assert ("scipy", "1.9.0") in packages
            assert ("matplotlib", "3.5.0") in packages
            assert ("flask", "") in packages


def test_parse_requirements_txt_oserror():
    with patch("os.path.exists", return_value=True):
        with patch("builtins.open", side_effect=OSError):
            assert (
                dependency_risk_report.parse_requirements_txt("requirements.txt") == []
            )


# Test cases for query_pypi_package
@patch("urllib.request.urlopen")
@patch("urllib.request.Request")
def test_query_pypi_package_success(mock_request, mock_urlopen):
    mock_response = MagicMock()
    mock_response.read.return_value = (
        b'{"info": {"version": "2.28.1", "requires_python": ">=3.7"}}'
    )
    mock_urlopen.return_value.__enter__.return_value = mock_response

    res = dependency_risk_report.query_pypi_package("requests")
    assert res == {"info": {"version": "2.28.1", "requires_python": ">=3.7"}}
    mock_request.assert_called_once_with(
        "https://pypi.org/pypi/requests/json",
        headers={"User-Agent": "DependencyRiskReport/1.0"},
    )


@patch("urllib.request.urlopen")
def test_query_pypi_package_failure(mock_urlopen):
    mock_urlopen.side_effect = urllib.error.URLError("connection failed")
    assert dependency_risk_report.query_pypi_package("requests") is None


# Test cases for calculate_upgrade_risk
def test_calculate_upgrade_risk():
    # Missing info
    assert dependency_risk_report.calculate_upgrade_risk("", "1.0.0") == (
        "Unknown",
        "Missing version specifications to assess risk",
    )
    assert dependency_risk_report.calculate_upgrade_risk("1.0.0", "") == (
        "Unknown",
        "Missing version specifications to assess risk",
    )

    # Same version
    assert dependency_risk_report.calculate_upgrade_risk("1.0.0", "1.0.0") == (
        "None",
        "Up to date",
    )

    # Major version bump
    msg_major = (
        "Major version bump (1.0.0 -> 2.0.0). Breaking changes and API re-writes "
        "likely."
    )
    assert dependency_risk_report.calculate_upgrade_risk("1.0.0", "2.0.0") == (
        "High",
        msg_major,
    )
    msg_major_short = (
        "Major version bump (1.0 -> 2.0). Breaking changes and API re-writes " "likely."
    )
    assert dependency_risk_report.calculate_upgrade_risk("1.0", "2.0") == (
        "High",
        msg_major_short,
    )

    # Minor version bump
    msg_minor = (
        "Minor version bump (1.0.0 -> 1.1.0). New features, minor deprecation " "risks."
    )
    assert dependency_risk_report.calculate_upgrade_risk("1.0.0", "1.1.0") == (
        "Medium",
        msg_minor,
    )

    # Patch version bump / low risk
    assert dependency_risk_report.calculate_upgrade_risk("1.0.0", "1.0.1") == (
        "Low",
        "Patch/bugfix update (1.0.0 -> 1.0.1). Safe to upgrade.",
    )

    # Invalid SemVer fallback
    msg_invalid = (
        "Major version bump (invalid -> 1.0.0). Breaking changes and API "
        "re-writes likely."
    )
    assert dependency_risk_report.calculate_upgrade_risk("invalid", "1.0.0") == (
        "High",
        msg_invalid,
    )

    class BadStr(str):
        def split(self, sep):
            class BadList:
                def __bool__(self):
                    raise ValueError("mock error")

                def __len__(self):
                    raise ValueError("mock error")

                def __getitem__(self, index):
                    raise ValueError("mock error")

            return BadList()

    assert dependency_risk_report.calculate_upgrade_risk(BadStr("1.0"), "1.0.0") == (
        "Low",
        "Outdated version gap (1.0 -> 1.0.0). SemVer unparseable.",
    )


# Test cases for main entrypoint
@patch("sys.argv", ["dependency_risk_report.py", "nonexistent.txt"])
@patch("os.path.exists", return_value=False)
def test_main_file_not_found(mock_exists):
    with pytest.raises(SystemExit) as exc_info:
        dependency_risk_report.main()
    assert exc_info.value.code == 1


@patch("sys.argv", ["dependency_risk_report.py", "reqs.txt"])
@patch("os.path.exists", return_value=True)
@patch("dependency_risk_report.parse_requirements_txt", return_value=[])
def test_main_no_packages(mock_parse, mock_exists):
    with pytest.raises(SystemExit) as exc_info:
        dependency_risk_report.main()
    assert exc_info.value.code == 0


@patch("sys.argv", ["dependency_risk_report.py", "reqs.txt"])
@patch("os.path.exists", return_value=True)
@patch(
    "dependency_risk_report.parse_requirements_txt",
    return_value=[("requests", "2.28.0"), ("numpy", "1.20.0"), ("badpkg", "1.0")],
)
@patch("dependency_risk_report.query_pypi_package")
def test_main_success(mock_query, mock_parse, mock_exists):
    def side_effect(pkg_name):
        if pkg_name == "requests":
            return {"info": {"version": "2.29.0", "requires_python": ">=3.7"}}
        elif pkg_name == "numpy":
            return {"info": {"version": "2.0.0", "requires_python": ">=3.8"}}
        return None

    mock_query.side_effect = side_effect

    with patch("sys.stdout"):
        dependency_risk_report.main()
