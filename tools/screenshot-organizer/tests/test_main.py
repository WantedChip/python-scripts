"""Unit tests for the CLI Screenshot Organizer."""

import argparse
import json
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from screenshot_organizer.main import ScreenshotOrganizer, parse_app_keywords


def test_parse_app_keywords_none() -> None:
    """Test parse_app_keywords with None input."""
    assert parse_app_keywords(None) is None


def test_parse_app_keywords_string_format() -> None:
    """Test parsing app keywords from string format."""
    res = parse_app_keywords("Chrome=chrome|google,Discord=discord")
    assert res == {"Chrome": ["chrome", "google"], "Discord": ["discord"]}


def test_parse_app_keywords_invalid_string() -> None:
    """Test parse_app_keywords raises ArgumentTypeError on invalid string."""
    with pytest.raises(argparse.ArgumentTypeError):
        parse_app_keywords("invalid_format_without_equals")


def test_parse_app_keywords_json_file(tmp_path: Path) -> None:
    """Test parsing app keywords from a JSON file."""
    json_file = tmp_path / "keywords.json"
    data = {"VSCode": ["code", "visual studio"], "Slack": "slack"}
    with open(json_file, "w", encoding="utf-8") as f:
        json.dump(data, f)

    res = parse_app_keywords(str(json_file))
    assert res == {"VSCode": ["code", "visual studio"], "Slack": ["slack"]}


def test_parse_app_keywords_invalid_json(tmp_path: Path) -> None:
    """Test parse_app_keywords with invalid JSON file."""
    bad_file = tmp_path / "bad.json"
    with open(bad_file, "w", encoding="utf-8") as f:
        f.write("invalid json content")

    with pytest.raises(argparse.ArgumentTypeError):
        parse_app_keywords(str(bad_file))


def test_parse_app_keywords_not_file_or_format() -> None:
    """Test parse_app_keywords with invalid path and format."""
    with pytest.raises(argparse.ArgumentTypeError):
        parse_app_keywords("non_existent_file_path.json")


def test_is_tesseract_available_true() -> None:
    """Test _check_ocr_availability when tesseract is found."""
    with patch("pytesseract.get_tesseract_version", return_value="5.0.0"):
        organizer = ScreenshotOrganizer(Path("src"), Path("dst"))
        assert organizer.ocr_available is True


def test_is_tesseract_available_false() -> None:
    """Test _check_ocr_availability when tesseract is missing."""
    with patch("pytesseract.get_tesseract_version", side_effect=Exception("not found")):
        organizer = ScreenshotOrganizer(Path("src"), Path("dst"))
        assert organizer.ocr_available is False


def test_get_image_files_nonexistent() -> None:
    """Test scanning source directory when it does not exist."""
    organizer = ScreenshotOrganizer(Path("nonexistent_path_xyz"), Path("dst"))
    assert not organizer.get_image_files()


@patch.object(Path, "iterdir")
@patch.object(Path, "exists", return_value=True)
@patch.object(Path, "is_file", return_value=True)
@patch("os.stat")
def test_get_image_files_filtering(
    mock_stat: MagicMock,
    mock_is_file: MagicMock,  # pylint: disable=unused-argument
    mock_exists: MagicMock,  # pylint: disable=unused-argument
    mock_iterdir: MagicMock,
) -> None:
    """Test that image scan correctly filters and sorts images."""
    mock_iterdir.return_value = [
        Path("src/img1.png"),
        Path("src/img2.jpg"),
        Path("src/doc1.txt"),
        Path("src/img3.WEBP"),
    ]

    # Setup stat return values to mock creation times
    stat_1 = MagicMock()
    stat_1.st_mtime = 1000
    stat_1.st_ctime = 1000

    stat_2 = MagicMock()
    stat_2.st_mtime = 500
    stat_2.st_ctime = 500

    stat_3 = MagicMock()
    stat_3.st_mtime = 2000
    stat_3.st_ctime = 2000

    mock_stat.side_effect = lambda *args, **kwargs: {
        "img1.png": stat_1,
        "img2.jpg": stat_2,
        "img3.WEBP": stat_3,
    }[Path(args[0]).name]

    organizer = ScreenshotOrganizer(Path("src"), Path("dst"))
    files = organizer.get_image_files()

    # Should only include images, sorted by mtime (img2 first, then img1, then img3)
    assert len(files) == 3
    assert files[0] == Path("src/img2.jpg")
    assert files[1] == Path("src/img1.png")
    assert files[2] == Path("src/img3.WEBP")


def test_extract_date_from_filename() -> None:
    """Test date parsing from filename regexes."""
    organizer = ScreenshotOrganizer(Path("src"), Path("dst"))

    # Test YYYY-MM-DD format
    d1 = organizer.extract_date(Path("Screenshot_2026-07-10_12345.png"))
    assert d1.strftime("%Y-%m-%d") == "2026-07-10"

    # Test YYYYMMDD format
    d2 = organizer.extract_date(Path("Screenshot_20260710-12345.png"))
    assert d2.strftime("%Y-%m-%d") == "2026-07-10"


@patch("PIL.Image.open")
def test_extract_date_from_exif(mock_open: MagicMock) -> None:
    """Test date extraction from image EXIF data."""
    organizer = ScreenshotOrganizer(Path("src"), Path("dst"))

    mock_img = MagicMock()
    # Mock Exif datetime tag (DateTimeOriginal is tag 36867)
    mock_img.getexif.return_value = {36867: "2026:07:10 12:00:00"}
    mock_open.return_value.__enter__.return_value = mock_img

    d = organizer.extract_date(Path("Screenshot.jpg"))
    assert d.strftime("%Y-%m-%d") == "2026-07-10"


@patch.object(Path, "stat")
def test_extract_date_mtime_fallback(mock_stat: MagicMock) -> None:
    """Test date extraction falls back to filesystem mtime/ctime."""
    organizer = ScreenshotOrganizer(Path("src"), Path("dst"))

    stat_mock = MagicMock()
    stat_mock.st_mtime = 1783684800  # Unix timestamp for 2026-07-10
    stat_mock.st_ctime = 1783684800
    mock_stat.return_value = stat_mock

    d = organizer.extract_date(Path("Screenshot_random_name.png"))
    assert d.strftime("%Y-%m-%d") == "2026-07-10"


def test_extract_app_from_filename() -> None:
    """Test app name extraction from trailing markers in filename."""
    # Dash format
    assert (
        ScreenshotOrganizer.extract_app_from_filename(
            "Screenshot 2026-07-10 - Google Chrome.png"
        )
        == "Google Chrome"
    )

    # Parentheses format
    assert (
        ScreenshotOrganizer.extract_app_from_filename(
            "Screenshot 2026-07-10 (VS Code).png"
        )
        == "VS Code"
    )

    # No app name
    assert (
        ScreenshotOrganizer.extract_app_from_filename("Screenshot 2026-07-10.png")
        is None
    )


@patch("pytesseract.image_to_string")
@patch("PIL.Image.open")
def test_extract_app_from_ocr(mock_open: MagicMock, mock_ocr: MagicMock) -> None:
    """Test OCR app name extraction based on keywords."""
    organizer = ScreenshotOrganizer(Path("src"), Path("dst"))
    organizer.ocr_available = True

    # Setup mock image open
    mock_open.return_value.__enter__.return_value = MagicMock()

    # Mock OCR output text containing keywords
    mock_ocr.return_value = "This is a screenshot of vscode editing python scripts"

    app = organizer.extract_app_from_ocr(Path("Screenshot.png"))
    # 'vscode' should match "VS Code"
    assert app == "VS Code"


@patch("pytesseract.image_to_string")
@patch("PIL.Image.open")
def test_extract_app_from_ocr_longest_match(
    mock_open: MagicMock, mock_ocr: MagicMock
) -> None:
    """Test OCR matches the longest keyword first to prevent generic overlap matches."""
    organizer = ScreenshotOrganizer(Path("src"), Path("dst"))
    organizer.ocr_available = True

    mock_open.return_value.__enter__.return_value = MagicMock()
    # Contains both 'chrome' and 'google chrome'
    mock_ocr.return_value = "Using Google Chrome to search for python packages"

    app = organizer.extract_app_from_ocr(Path("Screenshot.png"))
    # 'google chrome' is longer than 'chrome', both map to Chrome, but check logic
    assert app == "Chrome"


def test_hamming_distance() -> None:
    """Test hamming distance calculation between hex strings."""
    # Identical
    assert ScreenshotOrganizer.hamming_distance("0000", "0000") == 0
    # 1 bit difference (1 vs 0)
    assert ScreenshotOrganizer.hamming_distance("0001", "0000") == 1
    # 4 bits difference (f vs 0 -> 1111 vs 0000)
    assert ScreenshotOrganizer.hamming_distance("000f", "0000") == 4
    # Invalid hash
    assert ScreenshotOrganizer.hamming_distance("invalid", "0000") == 999


@patch("PIL.Image.open")
def test_compute_dhash(mock_open: MagicMock) -> None:
    """Test dHash computation."""
    mock_img = MagicMock()
    # Mock image resize
    mock_resized = MagicMock()
    # Mock grayscale pixel data (9x8 = 72 pixels)
    # We will generate a repeating pattern where half pixels are brighter
    mock_resized.getdata.return_value = [100 if i % 2 == 0 else 50 for i in range(72)]
    mock_img.convert.return_value.resize.return_value = mock_resized
    mock_open.return_value.__enter__.return_value = mock_img

    dhash = ScreenshotOrganizer.compute_dhash(Path("Screenshot.png"))
    assert dhash is not None
    assert len(dhash) == 16


@patch("PIL.Image.open", side_effect=Exception("could not open image"))
def test_compute_dhash_error(_mock_open: MagicMock) -> None:
    """Test dHash computation fails gracefully when image cannot be read."""
    assert ScreenshotOrganizer.compute_dhash(Path("Screenshot.png")) is None


def test_group_by_similarity() -> None:
    """Test duplicate similarity clustering."""
    organizer = ScreenshotOrganizer(Path("src"), Path("dst"), similarity_threshold=4)

    # Mock compute_dhash to return specific hashes
    hash_a = "0000000000000000"
    hash_b = "0000000000000003"  # Hamming distance = 2 (under threshold)
    hash_c = "00000000000000ff"  # Hamming distance = 8 (above threshold)

    files = [Path("imgA.png"), Path("imgB.png"), Path("imgC.png")]

    with patch.object(
        organizer,
        "compute_dhash",
        side_effect=lambda path: {
            Path("imgA.png"): hash_a,
            Path("imgB.png"): hash_b,
            Path("imgC.png"): hash_c,
        }[path],
    ):
        primaries, duplicates_map = organizer.group_by_similarity(files)

        # imgA and imgB are similar, so imgA is primary, imgB is duplicate
        # imgC is unique primary
        assert len(primaries) == 2
        assert Path("imgA.png") in primaries
        assert Path("imgC.png") in primaries
        assert Path("imgB.png") not in primaries

        assert Path("imgA.png") in duplicates_map
        assert duplicates_map[Path("imgA.png")] == [Path("imgB.png")]


def test_determine_dest_folder() -> None:
    """Test calculating sorting destination path."""
    organizer = ScreenshotOrganizer(
        Path("src"),
        Path("dst"),
        by_rules=["date", "app"],
        date_format="YYYY-MM-DD",
    )

    # Mock extract_date and get_app_clue
    fixed_date = datetime(2026, 7, 10)
    with patch.object(organizer, "extract_date", return_value=fixed_date), patch.object(
        organizer, "get_app_clue", return_value="Google Chrome"
    ):
        dest = organizer.determine_dest_folder(Path("Screenshot.png"))
        assert dest == Path("dst/2026-07-10/Google Chrome")


def test_get_unique_target(tmp_path: Path) -> None:
    """Test get_unique_target increments filenames correctly."""
    base_file = tmp_path / "test.png"
    # Create the original file
    base_file.touch()

    # Should append _1
    target1 = ScreenshotOrganizer.get_unique_target(base_file)
    assert target1 == tmp_path / "test_1.png"

    # Create the _1 file too
    target1.touch()

    # Should append _2
    target2 = ScreenshotOrganizer.get_unique_target(base_file)
    assert target2 == tmp_path / "test_2.png"


@patch("shutil.move")
@patch("shutil.copy2")
@patch.object(Path, "mkdir")
def test_execute_file_action_copy(
    mock_mkdir: MagicMock, mock_copy: MagicMock, mock_move: MagicMock
) -> None:
    """Test file action: copy."""
    organizer = ScreenshotOrganizer(Path("src"), Path("dst"), action="copy")
    organizer.execute_file_action(Path("src/img.png"), Path("dst/img.png"))

    mock_mkdir.assert_called_once_with(parents=True, exist_ok=True)
    mock_copy.assert_called_once_with(Path("src/img.png"), Path("dst/img.png"))
    mock_move.assert_not_called()


@patch("shutil.move")
@patch("shutil.copy2")
@patch.object(Path, "mkdir")
def test_execute_file_action_move(
    mock_mkdir: MagicMock, mock_copy: MagicMock, mock_move: MagicMock
) -> None:
    """Test file action: move."""
    organizer = ScreenshotOrganizer(Path("src"), Path("dst"), action="move")
    organizer.execute_file_action(Path("src/img.png"), Path("dst/img.png"))

    mock_mkdir.assert_called_once_with(parents=True, exist_ok=True)
    mock_move.assert_called_once_with("src\\img.png", "dst\\img.png")
    mock_copy.assert_not_called()


@patch("shutil.move")
@patch("shutil.copy2")
@patch.object(Path, "mkdir")
def test_execute_file_action_dry_run(
    mock_mkdir: MagicMock, mock_copy: MagicMock, mock_move: MagicMock
) -> None:
    """Test file action in dry-run mode (no actual changes)."""
    organizer = ScreenshotOrganizer(Path("src"), Path("dst"), dry_run=True)
    organizer.execute_file_action(Path("src/img.png"), Path("dst/img.png"))

    mock_mkdir.assert_not_called()
    mock_copy.assert_not_called()
    mock_move.assert_not_called()


@patch("builtins.open")
@patch("json.dump")
@patch.object(ScreenshotOrganizer, "extract_date_from_mtime")
@patch.object(ScreenshotOrganizer, "get_image_files")
@patch.object(ScreenshotOrganizer, "group_by_similarity")
@patch.object(ScreenshotOrganizer, "determine_dest_folder")
@patch.object(ScreenshotOrganizer, "execute_file_action")
@patch.object(Path, "mkdir")
# pylint: disable=too-many-positional-arguments
def test_organize_flow(  # pylint: disable=too-many-arguments
    _mock_mkdir: MagicMock,
    mock_execute: MagicMock,
    mock_determine: MagicMock,
    mock_group: MagicMock,
    mock_get_files: MagicMock,
    mock_mtime: MagicMock,
    _mock_json_dump: MagicMock,
    _mock_open: MagicMock,
) -> None:
    """Test the full organize workflow."""
    organizer = ScreenshotOrganizer(Path("src"), Path("dst"))

    files = [Path("src/imgA.png"), Path("src/imgB.png")]
    mock_get_files.return_value = files
    mock_mtime.return_value = datetime(2026, 7, 10)

    # Setup duplicates mapping: imgB is a duplicate of imgA
    mock_group.return_value = (
        [Path("src/imgA.png")],
        {Path("src/imgA.png"): [Path("src/imgB.png")]},
    )
    mock_determine.return_value = Path("dst/2026-07-10/Chrome")

    # Run organize
    organizer.organize()

    # Check that both files are executed
    # (imgA moved to target, imgB moved to duplicates folder)
    assert mock_execute.call_count == 2
    mock_execute.assert_any_call(
        Path("src/imgA.png"), Path("dst/2026-07-10/Chrome/imgA.png")
    )
    mock_execute.assert_any_call(
        Path("src/imgB.png"), Path("dst/duplicates/imgA/imgB.png")
    )
