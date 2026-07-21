import os
import sqlite3
import sys
from unittest.mock import ANY, MagicMock, patch

import pytest

# Mock PIL and pytesseract before importing screenshot_search
mock_pil = MagicMock()
mock_pytesseract = MagicMock()
sys.modules["PIL"] = mock_pil
sys.modules["PIL.Image"] = mock_pil.Image
sys.modules["pytesseract"] = mock_pytesseract

# Add the parent directory of this test file to sys.path so we can import safe
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import screenshot_search  # noqa: E402

screenshot_search.HAS_LIBS = True
screenshot_search.Image = mock_pil.Image
screenshot_search.pytesseract = mock_pytesseract


@pytest.fixture
def temp_db(tmp_path):
    db_path = str(tmp_path / "test_screenshots.db")
    screenshot_search.init_db(db_path)
    return db_path


def test_init_db(tmp_path):
    db_path = str(tmp_path / "init.db")
    screenshot_search.init_db(db_path)
    assert os.path.exists(db_path)

    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='screenshots'"
        )
        assert cursor.fetchone() is not None


def test_get_default_screenshots_dir():
    with patch("os.path.expanduser", return_value="C:\\Users\\Test"), patch(
        "os.path.exists",
        side_effect=lambda p: p == "C:\\Users\\Test\\Pictures\\Screenshots",
    ):
        assert (
            screenshot_search.get_default_screenshots_dir()
            == "C:\\Users\\Test\\Pictures\\Screenshots"
        )

    with patch("os.path.expanduser", return_value="C:\\Users\\Test"), patch(
        "os.path.exists", side_effect=lambda p: p == "C:\\Users\\Test\\Pictures"
    ):
        assert (
            screenshot_search.get_default_screenshots_dir()
            == "C:\\Users\\Test\\Pictures"
        )

    with patch("os.path.expanduser", return_value="C:\\Users\\Test"), patch(
        "os.path.exists", return_value=False
    ):
        assert screenshot_search.get_default_screenshots_dir() == "."


def test_ocr_image_tesseract_not_found():
    with patch("shutil.which", return_value=None), patch(
        "os.path.exists", return_value=False
    ):
        res = screenshot_search.ocr_image("dummy.png")
        assert "Tesseract binary not found" in res


def test_ocr_image_tesseract_win_path():
    with patch("shutil.which", return_value=None), patch(
        "os.path.exists", side_effect=lambda p: "Tesseract-OCR" in p
    ):
        mock_pytesseract.image_to_string.return_value = "hello from windows tesseract"
        res = screenshot_search.ocr_image("dummy.png")
        assert res == "hello from windows tesseract"
        assert mock_pytesseract.pytesseract.tesseract_cmd is not None


def test_ocr_image_success():
    with patch("shutil.which", return_value="/usr/bin/tesseract"):
        mock_pytesseract.image_to_string.return_value = "ocr result text"
        res = screenshot_search.ocr_image("dummy.png")
        assert res == "ocr result text"


def test_ocr_image_exception():
    with patch("shutil.which", return_value="/usr/bin/tesseract"):
        mock_pil.Image.open.side_effect = OSError("File corrupted")
        res = screenshot_search.ocr_image("dummy.png")
        assert "Error performing OCR" in res
        mock_pil.Image.open.side_effect = None


def test_run_indexing(tmp_path, temp_db):
    scan_dir = str(tmp_path / "screenshots")
    os.makedirs(scan_dir)

    image_file = os.path.join(scan_dir, "shot1.png")
    txt_file = os.path.join(scan_dir, "shot2.txt")
    with open(image_file, "w") as f:
        f.write("png data")
    with open(txt_file, "w") as f:
        f.write("text data")

    with patch("screenshot_search.ocr_image", return_value="screenshot ocr text"):
        new_cnt, up_cnt = screenshot_search.run_indexing(scan_dir, temp_db)
        assert new_cnt == 1
        assert up_cnt == 0

        with sqlite3.connect(temp_db) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT path, ocr_text FROM screenshots")
            rows = cursor.fetchall()
            assert len(rows) == 1
            assert rows[0][0] == os.path.abspath(image_file)
            assert rows[0][1] == "screenshot ocr text"

        new_cnt2, up_cnt2 = screenshot_search.run_indexing(scan_dir, temp_db)
        assert new_cnt2 == 0
        assert up_cnt2 == 0

        future_time = os.path.getmtime(image_file) + 10
        os.utime(image_file, (future_time, future_time))

        new_cnt3, up_cnt3 = screenshot_search.run_indexing(scan_dir, temp_db)
        assert new_cnt3 == 0
        assert up_cnt3 == 1


def test_run_indexing_no_libs(temp_db):
    with patch("screenshot_search.HAS_LIBS", False):
        new_cnt, up_cnt = screenshot_search.run_indexing(".", temp_db)
        assert new_cnt == 0
        assert up_cnt == 0


def test_run_search(capsys, temp_db):
    screenshot_search.run_search("query", "non_existent_db.db")
    captured = capsys.readouterr()
    assert "No search index database found" in captured.err

    with sqlite3.connect(temp_db) as conn:
        cursor = conn.cursor()
        query1 = (
            "INSERT OR REPLACE INTO screenshots (path, last_modified, ocr_text) "
            "VALUES (?, ?, ?)"
        )
        cursor.execute(
            query1,
            (
                "/path/to/shot1.png",
                123.45,
                "This is a screenshot containing python code and tests",
            ),
        )
        query2 = (
            "INSERT OR REPLACE INTO screenshots (path, last_modified, ocr_text) "
            "VALUES (?, ?, ?)"
        )
        cursor.execute(query2, ("/path/to/shot2.png", 123.45, "Nothing interesting"))
        conn.commit()

    screenshot_search.run_search("python", temp_db)
    captured = capsys.readouterr()
    assert "SCREENSHOT SEARCH RESULTS FOR: 'python'" in captured.out
    assert "shot1.png" in captured.out
    assert "This is a screenshot containing python code and tests" in captured.out

    screenshot_search.run_search("javascript", temp_db)
    captured = capsys.readouterr()
    assert "No screenshots found matching: 'javascript'" in captured.out


@patch("screenshot_search.run_indexing")
@patch("screenshot_search.run_search")
@patch(
    "screenshot_search.get_default_screenshots_dir", return_value="default_screenshots"
)
def test_main_cli(mock_get_default, mock_run_search, mock_run_indexing):
    mock_run_indexing.return_value = (0, 0)
    with patch("sys.argv", ["screenshot_search.py", "my_query"]):
        screenshot_search.main()
        mock_run_indexing.assert_called_once()
        mock_run_search.assert_called_once_with("my_query", ANY)

    mock_run_indexing.reset_mock()
    mock_run_search.reset_mock()

    with patch(
        "sys.argv",
        ["screenshot_search.py", "-i", "-s", "custom_dir", "--db-path", "custom_db.db"],
    ):
        screenshot_search.main()
        mock_run_indexing.assert_called_once_with("custom_dir", "custom_db.db")
        mock_run_search.assert_not_called()
