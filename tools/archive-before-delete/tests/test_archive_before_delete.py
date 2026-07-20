import os
import sqlite3
import sys
import zipfile
from unittest.mock import patch

# Add target directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
import archive_before_delete  # noqa: E402


def test_init_db(tmp_path):
    db_path = os.path.join(tmp_path, "manifest.db")
    archive_before_delete.init_db(db_path)
    assert os.path.exists(db_path)

    # Verify tables
    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(quarantine)")
        columns = [row[1] for row in cursor.fetchall()]
        assert "id" in columns
        assert "original_path" in columns
        assert "archive_name" in columns
        assert "deleted_at" in columns
        assert "size_bytes" in columns
        assert "is_directory" in columns


def test_get_dir_size(tmp_path):
    sub_dir = tmp_path / "subdir"
    sub_dir.mkdir()
    file1 = sub_dir / "file1.txt"
    file1.write_text("hello")  # 5 bytes
    file2 = sub_dir / "file2.txt"
    file2.write_text("world!")  # 6 bytes

    size = archive_before_delete.get_dir_size(str(sub_dir))
    assert size == 11


def test_quarantine_path_nonexistent(tmp_path):
    db_path = os.path.join(tmp_path, "manifest.db")
    archive_before_delete.init_db(db_path)
    quar_dir = os.path.join(tmp_path, "quarantine")
    os.makedirs(quar_dir)

    non_existent = os.path.join(tmp_path, "nonexistent.txt")
    res = archive_before_delete.quarantine_path(
        non_existent, quar_dir, db_path, force=True
    )
    assert res is False


def test_quarantine_path_no_force_user_declines(tmp_path, capsys):
    db_path = os.path.join(tmp_path, "manifest.db")
    archive_before_delete.init_db(db_path)
    quar_dir = os.path.join(tmp_path, "quarantine")
    os.makedirs(quar_dir)

    target_file = tmp_path / "target.txt"
    target_file.write_text("data")

    with patch("builtins.input", return_value="n"):
        res = archive_before_delete.quarantine_path(
            str(target_file), quar_dir, db_path, force=False
        )
        assert res is False
        assert os.path.exists(target_file)
        captured = capsys.readouterr()
        assert "Skipped" in captured.out


def test_quarantine_path_file_success(tmp_path):
    db_path = os.path.join(tmp_path, "manifest.db")
    archive_before_delete.init_db(db_path)
    quar_dir = os.path.join(tmp_path, "quarantine")
    os.makedirs(quar_dir)

    target_file = tmp_path / "target.txt"
    target_file.write_text("data")

    res = archive_before_delete.quarantine_path(
        str(target_file), quar_dir, db_path, force=True
    )
    assert res is True
    assert not os.path.exists(target_file)

    # Verify db entry
    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        q_sql = (
            "SELECT original_path, size_bytes, is_directory, archive_name "
            "FROM quarantine"
        )
        cursor.execute(q_sql)
        row = cursor.fetchone()
        assert row is not None
        assert row[0] == os.path.abspath(target_file)
        assert row[1] == 4
        assert row[2] == 0
        archive_name = row[3]

    # Verify zip content
    archive_path = os.path.join(quar_dir, archive_name)
    assert os.path.exists(archive_path)
    with zipfile.ZipFile(archive_path, "r") as zipf:
        assert "target.txt" in zipf.namelist()
        assert zipf.read("target.txt").decode() == "data"


def test_quarantine_path_directory_success(tmp_path):
    db_path = os.path.join(tmp_path, "manifest.db")
    archive_before_delete.init_db(db_path)
    quar_dir = os.path.join(tmp_path, "quarantine")
    os.makedirs(quar_dir)

    target_dir = tmp_path / "target_dir"
    target_dir.mkdir()
    file1 = target_dir / "file1.txt"
    file1.write_text("content1")
    file2 = target_dir / "file2.txt"
    file2.write_text("content2")

    res = archive_before_delete.quarantine_path(
        str(target_dir), quar_dir, db_path, force=True
    )
    assert res is True
    assert not os.path.exists(target_dir)

    # Verify db entry
    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        q_sql = (
            "SELECT original_path, size_bytes, is_directory, archive_name "
            "FROM quarantine"
        )
        cursor.execute(q_sql)
        row = cursor.fetchone()
        assert row is not None
        assert row[0] == os.path.abspath(target_dir)
        assert row[1] == 16
        assert row[2] == 1
        archive_name = row[3]

    # Verify zip content
    archive_path = os.path.join(quar_dir, archive_name)
    assert os.path.exists(archive_path)
    with zipfile.ZipFile(archive_path, "r") as zipf:
        namelist = zipf.namelist()
        assert "target_dir/file1.txt" in namelist or "file1.txt" in namelist
        assert "target_dir/file2.txt" in namelist or "file2.txt" in namelist


def test_quarantine_path_zip_failure(tmp_path):
    db_path = os.path.join(tmp_path, "manifest.db")
    archive_before_delete.init_db(db_path)
    quar_dir = os.path.join(tmp_path, "quarantine")
    os.makedirs(quar_dir)

    target_file = tmp_path / "target.txt"
    target_file.write_text("data")

    with patch("zipfile.ZipFile", side_effect=Exception("Zip Failed")):
        res = archive_before_delete.quarantine_path(
            str(target_file), quar_dir, db_path, force=True
        )
        assert res is False
        assert os.path.exists(target_file)


def test_quarantine_path_delete_failure(tmp_path):
    db_path = os.path.join(tmp_path, "manifest.db")
    archive_before_delete.init_db(db_path)
    quar_dir = os.path.join(tmp_path, "quarantine")
    os.makedirs(quar_dir)

    target_file = tmp_path / "target.txt"
    target_file.write_text("data")

    orig_remove = os.remove

    def mock_remove(path, *args, **kwargs):
        if "target.txt" in str(path):
            raise OSError("Delete Failed")
        return orig_remove(path, *args, **kwargs)

    with patch("os.remove", side_effect=mock_remove):
        res = archive_before_delete.quarantine_path(
            str(target_file), quar_dir, db_path, force=True
        )
        assert res is False
        assert os.path.exists(target_file)


def test_run_list_empty(tmp_path, capsys):
    db_path = os.path.join(tmp_path, "manifest.db")
    archive_before_delete.init_db(db_path)

    archive_before_delete.run_list(db_path)
    captured = capsys.readouterr()
    assert "Quarantine is empty" in captured.out


def test_run_list_no_db(tmp_path, capsys):
    db_path = os.path.join(tmp_path, "nonexistent.db")
    archive_before_delete.run_list(db_path)
    captured = capsys.readouterr()
    assert "No quarantine history found" in captured.out


def test_run_list_with_records(tmp_path, capsys):
    db_path = os.path.join(tmp_path, "manifest.db")
    archive_before_delete.init_db(db_path)

    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        ins_sql = (
            "INSERT INTO quarantine (original_path, archive_name, deleted_at, "
            "size_bytes, is_directory) VALUES (?, ?, ?, ?, ?)"
        )
        cursor.execute(
            ins_sql,
            ("c:\\test\\file.txt", "file_123.zip", "2026-07-19T22:00:00", 1024, 0),
        )
        conn.commit()

    archive_before_delete.run_list(db_path)
    captured = capsys.readouterr()
    assert "ID" in captured.out
    assert "Deleted At" in captured.out
    assert "file.txt" in captured.out


def test_run_restore_no_db(tmp_path, capsys):
    db_path = os.path.join(tmp_path, "nonexistent_db.db")
    archive_before_delete.run_restore("1", str(tmp_path), db_path)
    captured = capsys.readouterr()
    assert "No quarantine manifest database found" in captured.err


def test_run_restore_not_found(tmp_path, capsys):
    db_path = os.path.join(tmp_path, "manifest.db")
    archive_before_delete.init_db(db_path)
    archive_before_delete.run_restore("999", str(tmp_path), db_path)
    captured = capsys.readouterr()
    assert "No matching quarantine record found" in captured.err


def test_run_restore_archive_missing(tmp_path, capsys):
    db_path = os.path.join(tmp_path, "manifest.db")
    archive_before_delete.init_db(db_path)

    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        ins_sql = (
            "INSERT INTO quarantine (original_path, archive_name, deleted_at, "
            "size_bytes, is_directory) VALUES (?, ?, ?, ?, ?)"
        )
        cursor.execute(
            ins_sql,
            ("c:\\test\\file.txt", "file_123.zip", "2026-07-19T22:00:00", 1024, 0),
        )
        conn.commit()

    archive_before_delete.run_restore("1", str(tmp_path), db_path)
    captured = capsys.readouterr()
    assert "Archive ZIP file not found" in captured.err


def test_run_restore_blocked_target(tmp_path, capsys):
    db_path = os.path.join(tmp_path, "manifest.db")
    archive_before_delete.init_db(db_path)

    existing_file = tmp_path / "already_exists.txt"
    existing_file.write_text("block")

    zip_path = tmp_path / "test_123.zip"
    zip_path.write_text("fakezip")

    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        ins_sql = (
            "INSERT INTO quarantine (original_path, archive_name, deleted_at, "
            "size_bytes, is_directory) VALUES (?, ?, ?, ?, ?)"
        )
        cursor.execute(
            ins_sql,
            (str(existing_file), "test_123.zip", "2026-07-19T22:00:00", 1024, 0),
        )
        conn.commit()

    archive_before_delete.run_restore("1", str(tmp_path), db_path)
    captured = capsys.readouterr()
    assert "already exists at target restore path" in captured.err


def test_run_restore_success(tmp_path):
    db_path = os.path.join(tmp_path, "manifest.db")
    archive_before_delete.init_db(db_path)

    quar_dir = tmp_path / "quarantine"
    quar_dir.mkdir()

    original_file = tmp_path / "orig.txt"
    zip_name = "orig_123.zip"
    zip_path = quar_dir / zip_name
    with zipfile.ZipFile(zip_path, "w") as zipf:
        zipf.writestr("orig.txt", "restored content")

    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        ins_sql = (
            "INSERT INTO quarantine (original_path, archive_name, deleted_at, "
            "size_bytes, is_directory) VALUES (?, ?, ?, ?, ?)"
        )
        cursor.execute(
            ins_sql,
            (str(original_file), zip_name, "2026-07-19T22:00:00", 16, 0),
        )
        conn.commit()

    archive_before_delete.run_restore("1", str(quar_dir), db_path)

    assert os.path.exists(original_file)
    with open(original_file, "r") as f:
        assert f.read() == "restored content"

    assert not os.path.exists(zip_path)

    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT count(*) FROM quarantine")
        assert cursor.fetchone()[0] == 0


def test_main_list(tmp_path):
    with patch("archive_before_delete.run_list") as mock_list, patch(
        "sys.argv", ["archive_before_delete.py", "-l", "-q", str(tmp_path)]
    ):
        archive_before_delete.main()
        mock_list.assert_called_once()


def test_main_restore(tmp_path):
    with patch("archive_before_delete.run_restore") as mock_restore, patch(
        "sys.argv", ["archive_before_delete.py", "-r", "12", "-q", str(tmp_path)]
    ):
        archive_before_delete.main()
        mock_restore.assert_called_once_with(
            "12", str(tmp_path), os.path.join(str(tmp_path), ".quarantine_manifest.db")
        )


def test_main_quarantine(tmp_path):
    target = tmp_path / "to_delete.txt"
    target.write_text("hello")
    with patch(
        "archive_before_delete.quarantine_path", return_value=True
    ) as mock_quar, patch(
        "sys.argv",
        ["archive_before_delete.py", str(target), "-q", str(tmp_path), "-f"],
    ):
        archive_before_delete.main()
        mock_quar.assert_called_once_with(
            str(target),
            str(tmp_path),
            os.path.join(str(tmp_path), ".quarantine_manifest.db"),
            True,
        )
