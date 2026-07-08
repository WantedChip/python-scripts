"""Tests for Downloads Folder Auto-Organizer."""

from datetime import datetime
import json
from pathlib import Path
import sys
from typing import Any

import pytest


# Ensure parent folder is in path for imports to resolve.
# The actual script location will be in 'automation/downloads-organizer/'
# but for local proposed testing, we mock/import from path.
sys.path.insert(0, str(Path(__file__).parent.parent))

from downloads_organizer import FolderOrganizer


def test_classify_file(tmp_path: Path) -> None:
    """Tests if files are correctly classified based on extension and rules."""
    organizer = FolderOrganizer(source=tmp_path)

    assert organizer.classify_file(Path("photo.png")) == "Images"
    assert organizer.classify_file(Path("document.pdf")) == "Documents"
    assert organizer.classify_file(Path("song.mp3")) == "Audio"
    assert organizer.classify_file(Path("movie.mp4")) == "Video"
    assert organizer.classify_file(Path("archive.zip")) == "Archives"
    assert organizer.classify_file(Path("installer.msi")) == "Executables"
    assert organizer.classify_file(Path("random.xyz")) == "Others"


def test_should_ignore(tmp_path: Path) -> None:
    """Tests if temp files, directories, and ignored patterns are skipped."""
    organizer = FolderOrganizer(source=tmp_path)

    # Temporary download files
    assert organizer.should_ignore(Path("file.crdownload")) is True
    assert organizer.should_ignore(Path("file.part")) is True
    assert organizer.should_ignore(Path("file.tmp")) is True

    # Ignored system files
    assert organizer.should_ignore(Path("desktop.ini")) is True
    assert organizer.should_ignore(Path(".DS_Store")) is True

    # Already organized directory checks (dest dir inside source)
    images_dir = tmp_path / "Images"
    images_dir.mkdir()
    sorted_image = images_dir / "pic.jpg"
    sorted_image.write_text("dummy")

    assert organizer.should_ignore(sorted_image) is True

    # Unsorted file should NOT be ignored
    unsorted = tmp_path / "pic.jpg"
    unsorted.write_text("dummy")
    assert organizer.should_ignore(unsorted) is False


def test_conflict_resolution(tmp_path: Path) -> None:
    """Tests conflict resolution strategies (rename, overwrite, skip)."""
    # 1. Strategy: rename (default)
    org_rename = FolderOrganizer(source=tmp_path, conflict_strategy="rename")
    target = tmp_path / "existing.txt"
    target.write_text("existing")

    resolved_rename = org_rename.resolve_conflict(target)
    assert resolved_rename == tmp_path / "existing_1.txt"

    # Pre-create suffix file as well
    (tmp_path / "existing_1.txt").write_text("existing_1")
    resolved_rename_2 = org_rename.resolve_conflict(target)
    assert resolved_rename_2 == tmp_path / "existing_2.txt"

    # 2. Strategy: overwrite
    org_overwrite = FolderOrganizer(source=tmp_path, conflict_strategy="overwrite")
    resolved_overwrite = org_overwrite.resolve_conflict(target)
    assert resolved_overwrite == target

    # 3. Strategy: skip
    org_skip = FolderOrganizer(source=tmp_path, conflict_strategy="skip")
    resolved_skip = org_skip.resolve_conflict(target)
    assert resolved_skip is None


def test_custom_config(tmp_path: Path) -> None:
    """Tests if custom config JSON overrides classification rules."""
    config_file = tmp_path / "config.json"
    custom_rules = {
        "rules": [
            {"name": "Code", "extensions": [".py", ".js", ".cpp"]},
            {"name": "Data", "extensions": [".json", ".xml"]},
        ],
        "default_category": "Dump",
        "ignored_patterns": ["*.log"],
    }
    with open(config_file, "w", encoding="utf-8") as f:
        json.dump(custom_rules, f)

    organizer = FolderOrganizer(source=tmp_path, config_path=config_file)

    # New categories
    assert organizer.classify_file(Path("script.py")) == "Code"
    assert organizer.classify_file(Path("db.json")) == "Data"
    # Overridden default category
    assert organizer.classify_file(Path("image.png")) == "Dump"
    # Custom ignored pattern
    assert organizer.should_ignore(Path("test.log")) is True


def test_organize_file_actual_and_dry_run(tmp_path: Path) -> None:
    """Tests the organization of files, checking both dry-run and actual runs."""
    src_dir = tmp_path / "downloads"
    src_dir.mkdir()

    file_to_sort = src_dir / "document.pdf"
    file_to_sort.write_text("pdf contents")

    # 1. Dry run check
    org_dry = FolderOrganizer(source=src_dir, dry_run=True)
    success_dry = org_dry.organize_file(file_to_sort)

    assert success_dry is True
    assert file_to_sort.exists()  # should not be moved
    assert not (src_dir / "Documents" / "document.pdf").exists()

    # 2. Actual run check
    org_act = FolderOrganizer(source=src_dir, dry_run=False)
    success_act = org_act.organize_file(file_to_sort)

    assert success_act is True
    assert not file_to_sort.exists()  # should be moved
    assert (src_dir / "Documents" / "document.pdf").exists()


def test_date_grouping(tmp_path: Path) -> None:
    """Tests date grouping categorization (Category/YYYY-MM/)."""
    src_dir = tmp_path / "downloads"
    src_dir.mkdir()

    file_to_sort = src_dir / "pic.png"
    file_to_sort.write_text("png contents")

    # Get expected YYYY-MM string
    mtime = file_to_sort.stat().st_mtime
    expected_date = datetime.fromtimestamp(mtime).strftime("%Y-%m")

    org = FolderOrganizer(source=src_dir, date_grouping=True)
    success = org.organize_file(file_to_sort)

    assert success is True
    assert not file_to_sort.exists()
    assert (src_dir / "Images" / expected_date / "pic.png").exists()


def test_scan_and_organize(tmp_path: Path) -> None:
    """Tests scan_and_organize executes on all valid files in folder."""
    src_dir = tmp_path / "downloads"
    src_dir.mkdir()

    (src_dir / "photo.png").write_text("photo")
    (src_dir / "resume.pdf").write_text("resume")
    (src_dir / "temp.tmp").write_text("temp")  # ignored
    (src_dir / "readme.txt").write_text("readme")

    org = FolderOrganizer(source=src_dir)
    count = org.scan_and_organize()

    assert count == 3
    assert (src_dir / "Images" / "photo.png").exists()
    assert (src_dir / "Documents" / "resume.pdf").exists()
    assert (src_dir / "Documents" / "readme.txt").exists()
    assert (src_dir / "temp.tmp").exists()  # still in root


def test_is_file_stable_disabled(tmp_path: Path) -> None:
    """Tests that is_file_stable returns True if stability check is disabled."""
    organizer = FolderOrganizer(source=tmp_path, stability_check=False)
    file_path = tmp_path / "test.txt"
    # Even if file doesn't exist, if check is disabled it should return True
    assert organizer.is_file_stable(file_path) is True


def test_is_file_stable_not_exist(tmp_path: Path) -> None:
    """Tests that is_file_stable returns False if file does not exist."""
    organizer = FolderOrganizer(source=tmp_path, stability_check=True)
    file_path = tmp_path / "does_not_exist.txt"
    assert organizer.is_file_stable(file_path) is False


def test_is_file_stable_stabilizes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Tests is_file_stable when file size stabilizes and open succeeds."""
    organizer = FolderOrganizer(source=tmp_path, stability_check=True)
    file_path = tmp_path / "stable.txt"
    file_path.write_text("hello")

    sleep_called = 0
    def mock_sleep(seconds: float) -> None:
        nonlocal sleep_called
        sleep_called += 1

    monkeypatch.setattr("time.sleep", mock_sleep)

    assert organizer.is_file_stable(file_path, delay=0.1, retries=3) is True
    assert sleep_called == 1


def test_is_file_stable_unstable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Tests is_file_stable when file size keeps changing and never stabilizes."""
    organizer = FolderOrganizer(source=tmp_path, stability_check=True)
    file_path = tmp_path / "unstable.txt"
    file_path.write_text("hello")

    sizes = [1, 2, 3, 4]
    size_iter = iter(sizes)

    class MockStat:
        @property
        def st_size(self) -> int:
            return next(size_iter)

    original_stat = Path.stat
    def mock_stat(self, *args: Any, **kwargs: Any) -> Any:
        if str(self) == str(file_path):
            return MockStat()
        return original_stat(self, *args, **kwargs)

    monkeypatch.setattr(Path, "stat", mock_stat)
    monkeypatch.setattr("time.sleep", lambda s: None)

    assert organizer.is_file_stable(file_path, delay=0.1, retries=3) is False



def test_is_file_stable_locked(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Tests is_file_stable when file size is same but is locked by another process."""
    organizer = FolderOrganizer(source=tmp_path, stability_check=True)
    file_path = tmp_path / "locked.txt"
    file_path.write_text("hello")

    monkeypatch.setattr("time.sleep", lambda s: None)

    original_open = open
    def mock_open(path: Any, mode: str = "r", *args: Any, **kwargs: Any) -> Any:
        if str(path) == str(file_path) and "ab" in mode:
            raise PermissionError("Locked file")
        return original_open(path, mode, *args, **kwargs)

    monkeypatch.setattr("builtins.open", mock_open)

    assert organizer.is_file_stable(file_path, delay=0.1, retries=3) is False


def test_download_watch_handler(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Tests the FileSystemEventHandler subclass DownloadWatchHandler."""
    from downloads_organizer import HAS_WATCHDOG
    if not HAS_WATCHDOG:
        pytest.skip("Watchdog library is not installed.")

    from downloads_organizer import DownloadWatchHandler, FileSystemEvent

    organizer = FolderOrganizer(source=tmp_path)
    handler = DownloadWatchHandler(organizer)

    stable_called_with = []
    organize_called_with = []

    monkeypatch.setattr(
        organizer, "is_file_stable", lambda p: stable_called_with.append(p) or True
    )
    monkeypatch.setattr(
        organizer, "organize_file", lambda p: organize_called_with.append(p) or True
    )

    # 1. Test on_created with directory
    dir_event = FileSystemEvent(src_path=str(tmp_path / "subdir"))
    dir_event.is_directory = True
    handler.on_created(dir_event)
    assert len(stable_called_with) == 0

    # 2. Test on_created with file
    file_path = tmp_path / "photo.png"
    file_path.write_text("photo")
    file_event = FileSystemEvent(src_path=str(file_path))
    file_event.is_directory = False
    handler.on_created(file_event)
    assert len(stable_called_with) == 1
    assert stable_called_with[0] == file_path
    assert len(organize_called_with) == 1
    assert organize_called_with[0] == file_path

    # Reset lists
    stable_called_with.clear()
    organize_called_with.clear()

    # 3. Test on_moved with directory
    dir_moved = FileSystemEvent(
        src_path=str(tmp_path / "old_sub"),
        dest_path=str(tmp_path / "new_sub")
    )
    dir_moved.is_directory = True
    handler.on_moved(dir_moved)
    assert len(stable_called_with) == 0

    # 4. Test on_moved with file
    dest_path = tmp_path / "moved_photo.png"
    dest_path.write_text("moved_photo")
    file_moved = FileSystemEvent(
        src_path=str(file_path), dest_path=str(dest_path)
    )
    file_moved.is_directory = False
    handler.on_moved(file_moved)
    assert len(stable_called_with) == 1
    assert stable_called_with[0] == dest_path
    assert len(organize_called_with) == 1
    assert organize_called_with[0] == dest_path


def test_config_schema_validation_missing_rules(tmp_path: Path) -> None:
    """Tests that loading custom config missing 'rules' exits cleanly with 1."""
    config_file = tmp_path / "invalid_config.json"
    config_file.write_text(json.dumps({"default_category": "Others"}))

    with pytest.raises(SystemExit) as exc_info:
        FolderOrganizer(source=tmp_path, config_path=config_file)
    assert exc_info.value.code == 1


def test_config_schema_validation_rules_not_list(tmp_path: Path) -> None:
    """Tests that custom config with 'rules' not as a list exits cleanly with 1."""
    config_file = tmp_path / "invalid_config.json"
    config_file.write_text(json.dumps({"rules": "not a list"}))

    with pytest.raises(SystemExit) as exc_info:
        FolderOrganizer(source=tmp_path, config_path=config_file)
    assert exc_info.value.code == 1


def test_config_schema_validation_rule_missing_name(tmp_path: Path) -> None:
    """Tests that rule missing 'name' key exits cleanly with 1."""
    config_file = tmp_path / "invalid_config.json"
    config_file.write_text(json.dumps({"rules": [{"extensions": [".zip"]}]}))

    with pytest.raises(SystemExit) as exc_info:
        FolderOrganizer(source=tmp_path, config_path=config_file)
    assert exc_info.value.code == 1


def test_config_schema_validation_rule_missing_extensions_and_patterns(
    tmp_path: Path,
) -> None:
    """Tests rule missing both 'extensions' and 'patterns' keys exits with 1."""
    config_file = tmp_path / "invalid_config.json"
    config_file.write_text(json.dumps({"rules": [{"name": "MyRule"}]}))

    with pytest.raises(SystemExit) as exc_info:
        FolderOrganizer(source=tmp_path, config_path=config_file)
    assert exc_info.value.code == 1


def test_watch_mode_missing_directory(tmp_path: Path) -> None:
    """Tests that run_watch_mode exits with 1 when source dir does not exist."""
    from downloads_organizer import run_watch_mode
    non_existent = tmp_path / "does_not_exist"
    organizer = FolderOrganizer(source=non_existent)

    with pytest.raises(SystemExit) as exc_info:
        run_watch_mode(organizer)
    assert exc_info.value.code == 1


def test_is_file_stable_pure_mock(monkeypatch: pytest.MonkeyPatch) -> None:
    """Tests is_file_stable using pure mocks for exists, stat and sleep."""
    from unittest.mock import MagicMock
    mock_path = MagicMock(spec=Path)
    mock_path.exists.return_value = True

    mock_stat = MagicMock()
    mock_stat.st_size = 100
    mock_path.stat.return_value = mock_stat

    mock_open = MagicMock()
    monkeypatch.setattr("builtins.open", mock_open)

    sleep_calls = []
    monkeypatch.setattr("time.sleep", lambda s: sleep_calls.append(s))

    organizer = FolderOrganizer(source=Path("."))

    assert organizer.is_file_stable(mock_path, delay=0.1, retries=3) is True
    assert len(sleep_calls) == 1
    assert sleep_calls[0] == 0.1


def test_download_watch_handler_fails_stability(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Tests DownloadWatchHandler when file stability check fails."""
    from downloads_organizer import HAS_WATCHDOG
    if not HAS_WATCHDOG:
        pytest.skip("Watchdog library is not installed.")

    from downloads_organizer import DownloadWatchHandler, FileSystemEvent

    organizer = FolderOrganizer(source=tmp_path)
    handler = DownloadWatchHandler(organizer)

    is_stable_called = []
    def mock_is_file_stable(p):
        is_stable_called.append(p)
        return False

    monkeypatch.setattr(organizer, "is_file_stable", mock_is_file_stable)

    organize_called = []
    monkeypatch.setattr(
        organizer, "organize_file", lambda p: organize_called.append(p)
    )

    file_path = tmp_path / "unstable_photo.png"
    file_path.write_text("unstable")
    file_event = FileSystemEvent(src_path=str(file_path))
    file_event.is_directory = False
    handler.on_created(file_event)

    assert len(is_stable_called) == 1
    assert is_stable_called[0] == file_path
    assert len(organize_called) == 0

    is_stable_called.clear()
    dest_path = tmp_path / "unstable_moved_photo.png"
    dest_path.write_text("unstable_moved")
    file_moved = FileSystemEvent(
        src_path=str(file_path), dest_path=str(dest_path)
    )
    file_moved.is_directory = False
    handler.on_moved(file_moved)

    assert len(is_stable_called) == 1
    assert is_stable_called[0] == dest_path
    assert len(organize_called) == 0


def test_watchdog_ignore_check(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Tests that on_created and on_moved check should_ignore first and return early."""
    from downloads_organizer import HAS_WATCHDOG
    if not HAS_WATCHDOG:
        pytest.skip("Watchdog library is not installed.")

    from downloads_organizer import DownloadWatchHandler, FileSystemEvent

    organizer = FolderOrganizer(source=tmp_path)
    handler = DownloadWatchHandler(organizer)

    is_stable_called = []
    monkeypatch.setattr(
        organizer, "is_file_stable", lambda p: is_stable_called.append(p) or True
    )

    # We use an ignored extension (e.g. .tmp or .crdownload)
    ignored_path = tmp_path / "download.tmp"
    ignored_path.write_text("temp")

    # 1. Test on_created with ignored file
    event_created = FileSystemEvent(src_path=str(ignored_path))
    event_created.is_directory = False
    handler.on_created(event_created)
    assert len(is_stable_called) == 0

    # 2. Test on_moved with ignored file
    dest_ignored_path = tmp_path / "download_2.crdownload"
    dest_ignored_path.write_text("temp2")
    event_moved = FileSystemEvent(src_path=str(ignored_path), dest_path=str(dest_ignored_path))
    event_moved.is_directory = False
    handler.on_moved(event_moved)
    assert len(is_stable_called) == 0


def test_is_file_stable_deleted_during_check(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Tests that is_file_stable returns False early if the file is deleted during the check."""
    organizer = FolderOrganizer(source=tmp_path, stability_check=True)
    file_path = tmp_path / "dynamic.txt"
    file_path.write_text("start")

    sleep_called = 0
    def mock_sleep(seconds: float) -> None:
        nonlocal sleep_called
        sleep_called += 1
        # Delete the file during the sleep/retry loop
        if file_path.exists():
            file_path.unlink()

    monkeypatch.setattr("time.sleep", mock_sleep)

    # Run with retries=5, delay=0.1
    # On the first iteration, file exists, size is checked, sleep is called, which deletes the file.
    # On the second iteration, the loop checks not path.exists() and returns False immediately.
    assert organizer.is_file_stable(file_path, delay=0.1, retries=5) is False
    # The sleep should have been called only once, and we didn't do all 5 retries/sleeps
    assert sleep_called == 1


