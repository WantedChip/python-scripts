"""Unit tests for the file-origin script."""

import datetime
import os
import sys
from unittest.mock import MagicMock, mock_open, patch

# Insert parent dir to PATH to support folder-based import
sys.path.insert(0, "tools/file-origin")

from file_origin import (  # noqa: E402
    check_surrounding_clues,
    chrome_time_to_datetime,
    find_browser_dbs,
    get_zone_identifier,
    main,
    query_chrome_edge_history,
    query_firefox_history,
)


def test_get_zone_identifier_not_exist():
    with patch("os.path.exists", return_value=False):
        assert get_zone_identifier("dummy.txt") == {}


def test_get_zone_identifier_success():
    mock_data = """[ZoneTransfer]
ZoneId=3
ReferrerUrl=https://example.com/download
HostUrl=https://example.com/file.zip
"""
    m_open = mock_open(read_data=mock_data)
    with patch("os.path.exists", return_value=True), patch("builtins.open", m_open):
        details = get_zone_identifier("dummy.txt")
        assert details == {
            "ZoneId": "3",
            "ReferrerUrl": "https://example.com/download",
            "HostUrl": "https://example.com/file.zip",
        }


def test_get_zone_identifier_oserror():
    with patch("os.path.exists", return_value=True), patch(
        "builtins.open", side_effect=OSError("Access denied")
    ):
        assert get_zone_identifier("dummy.txt") == {}


def test_chrome_time_to_datetime():
    dt = chrome_time_to_datetime(0)
    assert dt == datetime.datetime(1601, 1, 1)

    dt_overflow = chrome_time_to_datetime(2**63 - 1)
    assert dt_overflow == datetime.datetime.min


def test_query_chrome_edge_history_not_exist():
    with patch("os.path.exists", return_value=False):
        assert query_chrome_edge_history("dummy_db.db", "file.txt") == []


def test_query_chrome_edge_history_shutil_error():
    with patch("os.path.exists", return_value=True), patch(
        "shutil.copy2", side_effect=OSError("copy failed")
    ):
        assert query_chrome_edge_history("dummy_db.db", "file.txt") == []


@patch("sqlite3.connect")
@patch("shutil.copy2")
@patch("os.path.exists", return_value=True)
@patch("os.remove")
def test_query_chrome_edge_history_success(
    mock_remove, mock_exists, mock_copy, mock_connect
):
    mock_conn = MagicMock()
    mock_connect.return_value.__enter__.return_value = mock_conn
    mock_cursor = mock_conn.cursor.return_value

    row1 = {
        "target_path": "C:\\Users\\User\\Downloads\\test.zip",
        "referrer": "https://referrer.com",
        "tab_url": "https://tab.com/download",
        "start_time": 13242000000000000,
        "received_bytes": 1024,
    }

    class MockRow:
        def __init__(self, d):
            self.d = d

        def __getitem__(self, key):
            return self.d[key]

    mock_cursor.fetchall.return_value = [MockRow(row1)]

    results = query_chrome_edge_history("dummy_db.db", "test.zip")
    assert len(results) == 1
    assert results[0]["target_path"] == "C:\\Users\\User\\Downloads\\test.zip"
    assert results[0]["referrer"] == "https://referrer.com"
    assert results[0]["tab_url"] == "https://tab.com/download"
    assert results[0]["received_bytes"] == 1024
    mock_remove.assert_called_once()


def test_query_firefox_history_not_exist():
    with patch("os.path.exists", return_value=False):
        assert query_firefox_history("dummy_db.sqlite", "file.txt") == []


def test_query_firefox_history_shutil_error():
    with patch("os.path.exists", return_value=True), patch(
        "shutil.copy2", side_effect=OSError("copy failed")
    ):
        assert query_firefox_history("dummy_db.sqlite", "file.txt") == []


@patch("sqlite3.connect")
@patch("shutil.copy2")
@patch("os.path.exists", return_value=True)
@patch("os.remove")
def test_query_firefox_history_success(
    mock_remove, mock_exists, mock_copy, mock_connect
):
    mock_conn = MagicMock()
    mock_connect.return_value.__enter__.return_value = mock_conn
    mock_cursor = mock_conn.cursor.return_value

    row1 = {
        "url": "https://firefox.com/file.zip",
        "title": "Firefox File",
        "visit_count": 1,
        "last_visit_date": 1626720000000000,
    }

    class MockRow:
        def __init__(self, d):
            self.d = d

        def __getitem__(self, key):
            return self.d[key]

    mock_cursor.fetchall.return_value = [MockRow(row1)]

    results = query_firefox_history("dummy_db.sqlite", "file.zip")
    assert len(results) == 1
    assert results[0]["target_path"] == "Firefox File"
    assert results[0]["tab_url"] == "https://firefox.com/file.zip"
    assert results[0]["received_bytes"] == 0
    mock_remove.assert_called_once()


def test_find_browser_dbs_no_userprofile():
    with patch.dict(os.environ, {}, clear=True):
        assert find_browser_dbs() == {}


@patch("os.path.exists")
@patch("glob.glob")
def test_find_browser_dbs_success(mock_glob, mock_exists):
    with patch.dict(os.environ, {"USERPROFILE": "C:\\Users\\MockUser"}):

        def exists_side_effect(path):
            if "Chrome" in path:
                return True
            return False

        mock_exists.side_effect = exists_side_effect
        mock_glob.return_value = [
            "C:\\Users\\MockUser\\AppData\\Roaming\\Mozilla\\Firefox\\"
            "Profiles\\xyz.default\\places.sqlite"
        ]

        dbs = find_browser_dbs()
        assert "chrome" in dbs
        assert "edge" not in dbs
        assert "firefox" in dbs
        user_profile = os.environ["USERPROFILE"]
        expected_chrome = os.path.join(
            user_profile,
            "AppData",
            "Local",
            "Google",
            "Chrome",
            "User Data",
            "Default",
            "History",
        )
        assert dbs["chrome"] == expected_chrome
        expected_ff = mock_glob.return_value[0]
        assert dbs["firefox"] == expected_ff


def test_check_surrounding_clues():
    mock_files = ["test.torrent", "test.txt", "test.json", "other.torrent", "test.py"]
    with patch("os.listdir", return_value=mock_files), patch(
        "os.path.dirname", return_value="dir"
    ), patch("os.path.basename", return_value="test.py"):

        clues = check_surrounding_clues("dir/test.py")
        assert len(clues) == 3
        assert any("torrent" in c for c in clues)
        assert any("description/log" in c for c in clues)
        assert any("metadata file" in c for c in clues)


@patch("os.path.exists", return_value=False)
def test_main_file_not_exist(mock_exists):
    with patch("sys.argv", ["file_origin.py", "missing.txt"]):
        try:
            main()
        except SystemExit as exc:
            assert exc.code == 1


@patch("os.path.exists", return_value=True)
@patch("os.path.abspath", return_value="C:\\MockDir\\test.zip")
@patch("os.stat")
@patch(
    "file_origin.get_zone_identifier",
    return_value={"ZoneId": "3", "HostUrl": "http://host.com"},
)
@patch("file_origin.find_browser_dbs", return_value={"chrome": "mock_chrome_db"})
@patch("file_origin.query_chrome_edge_history")
@patch("file_origin.check_surrounding_clues", return_value=["Found adjacent torrent"])
def test_main_success(
    mock_clues,
    mock_query,
    mock_find_dbs,
    mock_zone,
    mock_stat,
    mock_abspath,
    mock_exists,
):
    mock_query.return_value = [
        {
            "tab_url": "http://download.com/test.zip",
            "referrer": "http://referrer.com",
            "download_time": "2026-07-19 12:00:00",
            "received_bytes": 5000,
            "browser": "Chrome",
        }
    ]

    mock_stat_val = MagicMock()
    mock_stat_val.st_ctime = 1781870400
    mock_stat_val.st_mtime = 1781870400
    mock_stat.return_value = mock_stat_val

    with patch("sys.argv", ["file_origin.py", "test.zip"]):
        main()
        mock_query.assert_called_with(
            "mock_chrome_db", os.path.basename(mock_abspath.return_value)
        )


@patch("os.path.exists", return_value=True)
@patch("os.path.abspath", return_value="C:\\MockDir\\test.zip")
@patch("os.stat")
@patch("file_origin.get_zone_identifier", return_value={})
@patch("file_origin.query_chrome_edge_history", return_value=[])
@patch("file_origin.query_firefox_history", return_value=[])
@patch("file_origin.check_surrounding_clues", return_value=[])
def test_main_custom_browser_db(
    mock_clues, mock_ff, mock_chrome, mock_zone, mock_stat, mock_abspath, mock_exists
):
    mock_stat_val = MagicMock()
    mock_stat_val.st_ctime = 1781870400
    mock_stat_val.st_mtime = 1781870400
    mock_stat.return_value = mock_stat_val

    with patch(
        "sys.argv", ["file_origin.py", "test.zip", "--browser-db", "custom_db.sqlite"]
    ):
        main()
        expected_name = os.path.basename(mock_abspath.return_value)
        mock_chrome.assert_called_with("custom_db.sqlite", expected_name)
        mock_ff.assert_called_with("custom_db.sqlite", expected_name)
