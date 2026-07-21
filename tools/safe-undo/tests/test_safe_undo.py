import os
import sqlite3
import sys
import unittest
import zipfile
from unittest.mock import patch

import pytest

# Add the parent directory of this test file to sys.path so we can import safe_undo
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import safe_undo  # noqa: E402


@pytest.fixture
def temp_env(tmp_path):
    """Fixture to set up temporary DB and quarantine directories."""
    db_path = str(tmp_path / "test_manifest.db")
    quarantine_dir = str(tmp_path / "quarantine")
    os.makedirs(quarantine_dir, exist_ok=True)
    safe_undo.init_db(db_path)
    return db_path, quarantine_dir


def test_init_db(tmp_path):
    db_path = str(tmp_path / "test_init.db")
    safe_undo.init_db(db_path)
    assert os.path.exists(db_path)

    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='transactions'"
        )
        assert cursor.fetchone() is not None


def test_backup_to_quarantine_file(tmp_path, temp_env):
    _, quarantine_dir = temp_env
    src_file = tmp_path / "source.txt"
    src_file.write_text("hello world")

    zip_path, is_dir = safe_undo.backup_to_quarantine(str(src_file), quarantine_dir)

    assert not is_dir
    assert os.path.exists(zip_path)
    assert zip_path.endswith(".zip")
    assert quarantine_dir in zip_path

    with zipfile.ZipFile(zip_path, "r") as zipf:
        namelist = zipf.namelist()
        assert "source.txt" in namelist
        assert zipf.read("source.txt").decode() == "hello world"


def test_backup_to_quarantine_directory(tmp_path, temp_env):
    _, quarantine_dir = temp_env
    src_dir = tmp_path / "source_dir"
    os.makedirs(src_dir)
    file1 = src_dir / "file1.txt"
    file1.write_text("data1")
    sub_dir = src_dir / "subdir"
    os.makedirs(sub_dir)
    file2 = sub_dir / "file2.txt"
    file2.write_text("data2")

    zip_path, is_dir = safe_undo.backup_to_quarantine(str(src_dir), quarantine_dir)

    assert is_dir
    assert os.path.exists(zip_path)

    with zipfile.ZipFile(zip_path, "r") as zipf:
        namelist = zipf.namelist()
        assert "source_dir/file1.txt" in namelist
        assert "source_dir/subdir/file2.txt" in namelist
        assert zipf.read("source_dir/file1.txt").decode() == "data1"
        assert zipf.read("source_dir/subdir/file2.txt").decode() == "data2"


def test_backup_to_quarantine_error(tmp_path, temp_env):
    _, quarantine_dir = temp_env
    non_existent = str(tmp_path / "non_existent")

    with pytest.raises(OSError):
        safe_undo.backup_to_quarantine(non_existent, quarantine_dir)


def test_log_transaction(temp_env):
    db_path, _ = temp_env
    tx_id = safe_undo.log_transaction(
        db_path=db_path,
        action="delete",
        src_path="/dummy/src",
        dest_path=None,
        quarantine_path="/dummy/q.zip",
        is_dir=False,
    )
    assert tx_id > 0

    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        query = (
            "SELECT action, src_path, dest_path, quarantine_path, "
            "is_directory FROM transactions WHERE id = ?"
        )
        cursor.execute(query, (tx_id,))
        row = cursor.fetchone()
        assert row == ("delete", "/dummy/src", None, "/dummy/q.zip", 0)


def test_log_transaction_error():
    invalid_db = "/nonexistent_dir/no_db.db"
    tx_id = safe_undo.log_transaction(
        db_path=invalid_db,
        action="delete",
        src_path="/dummy/src",
        dest_path=None,
        quarantine_path="/dummy/q.zip",
        is_dir=False,
    )
    assert tx_id == -1


def test_safe_delete_file(tmp_path, temp_env):
    db_path, quarantine_dir = temp_env
    src_file = tmp_path / "to_delete.txt"
    src_file.write_text("delete me")

    assert os.path.exists(src_file)
    success = safe_undo.safe_delete(str(src_file), db_path, quarantine_dir)
    assert success
    assert not os.path.exists(src_file)

    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT action, src_path, is_directory FROM transactions")
        row = cursor.fetchone()
        assert row is not None
        assert row[0] == "delete"
        assert row[1] == os.path.abspath(src_file)
        assert row[2] == 0


def test_safe_delete_dir(tmp_path, temp_env):
    db_path, quarantine_dir = temp_env
    src_dir = tmp_path / "to_delete_dir"
    os.makedirs(src_dir)
    (src_dir / "sub.txt").write_text("hello")

    assert os.path.exists(src_dir)
    success = safe_undo.safe_delete(str(src_dir), db_path, quarantine_dir)
    assert success
    assert not os.path.exists(src_dir)

    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT action, src_path, is_directory FROM transactions")
        row = cursor.fetchone()
        assert row is not None
        assert row[0] == "delete"
        assert row[1] == os.path.abspath(src_dir)
        assert row[2] == 1


def test_safe_delete_nonexistent(temp_env):
    db_path, quarantine_dir = temp_env
    success = safe_undo.safe_delete("/non/existent/path", db_path, quarantine_dir)
    assert not success


def test_safe_move_file(tmp_path, temp_env):
    db_path, quarantine_dir = temp_env
    src_file = tmp_path / "src.txt"
    src_file.write_text("move me")
    dest_file = tmp_path / "dest" / "moved.txt"

    assert os.path.exists(src_file)
    assert not os.path.exists(dest_file)

    success = safe_undo.safe_move(
        str(src_file), str(dest_file), db_path, quarantine_dir
    )
    assert success
    assert not os.path.exists(src_file)
    assert os.path.exists(dest_file)
    assert dest_file.read_text() == "move me"

    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT action, src_path, dest_path FROM transactions")
        row = cursor.fetchone()
        assert row is not None
        assert row[0] == "move"
        assert row[1] == os.path.abspath(src_file)
        assert row[2] == os.path.abspath(dest_file)


def test_safe_move_nonexistent(tmp_path, temp_env):
    db_path, quarantine_dir = temp_env
    dest_file = tmp_path / "dest.txt"
    success = safe_undo.safe_move(
        "/non/existent/path", str(dest_file), db_path, quarantine_dir
    )
    assert not success


def test_rollback_delete(tmp_path, temp_env):
    db_path, quarantine_dir = temp_env
    src_file = tmp_path / "file.txt"
    src_file.write_text("rollback data")

    success = safe_undo.safe_delete(str(src_file), db_path, quarantine_dir)
    assert success
    assert not os.path.exists(src_file)

    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM transactions")
        tx_id = cursor.fetchone()[0]

    rollback_success = safe_undo.rollback_transaction(tx_id, db_path)
    assert rollback_success
    assert os.path.exists(src_file)
    assert src_file.read_text() == "rollback data"

    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM transactions")
        assert cursor.fetchone() is None


def test_rollback_move(tmp_path, temp_env):
    db_path, quarantine_dir = temp_env
    src_file = tmp_path / "src.txt"
    src_file.write_text("move rollback")
    dest_file = tmp_path / "dest.txt"

    success = safe_undo.safe_move(
        str(src_file), str(dest_file), db_path, quarantine_dir
    )
    assert success
    assert not os.path.exists(src_file)
    assert os.path.exists(dest_file)

    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM transactions")
        tx_id = cursor.fetchone()[0]

    rollback_success = safe_undo.rollback_transaction(tx_id, db_path)
    assert rollback_success
    assert os.path.exists(src_file)
    assert not os.path.exists(dest_file)
    assert src_file.read_text() == "move rollback"


def test_rollback_failures(tmp_path, temp_env):
    db_path, quarantine_dir = temp_env

    assert not safe_undo.rollback_transaction(999, db_path)

    tx_id = safe_undo.log_transaction(
        db_path, "delete", "/dummy/src", None, "/dummy/missing.zip", False
    )
    assert not safe_undo.rollback_transaction(tx_id, db_path)

    src_file = tmp_path / "exist.txt"
    src_file.write_text("original")
    zip_path, is_dir = safe_undo.backup_to_quarantine(str(src_file), quarantine_dir)
    os.remove(src_file)

    tx_id2 = safe_undo.log_transaction(
        db_path, "delete", str(src_file), None, zip_path, is_dir
    )
    src_file.write_text("conflict")

    assert not safe_undo.rollback_transaction(tx_id2, db_path)


def test_run_list(capsys, temp_env):
    db_path, _ = temp_env

    safe_undo.run_list(db_path)
    captured = capsys.readouterr()
    assert "No transactions logged" in captured.out

    tx_id = safe_undo.log_transaction(
        db_path=db_path,
        action="delete",
        src_path="short_path.txt",
        dest_path=None,
        quarantine_path="q.zip",
        is_dir=False,
    )

    long_src = (
        "very_long_directory_name_that_should_be_truncated_by_the_list_output_"
        "formatter.txt"
    )
    safe_undo.log_transaction(
        db_path=db_path,
        action="move",
        src_path=long_src,
        dest_path="another_very_long_destination_path_for_testing.txt",
        quarantine_path="q2.zip",
        is_dir=False,
    )

    safe_undo.run_list(db_path)
    captured = capsys.readouterr()
    assert "SAFE UNDO: FILESYSTEM TRANSACTIONS LOG" in captured.out
    assert str(tx_id) in captured.out
    assert "short_path.txt" in captured.out
    assert "..." in captured.out


@patch("safe_undo.init_db")
@patch("safe_undo.run_list")
@patch("safe_undo.rollback_transaction")
@patch("safe_undo.safe_delete")
@patch("safe_undo.safe_move")
def test_main_commands(
    mock_safe_move,
    mock_safe_delete,
    mock_rollback_transaction,
    mock_run_list,
    mock_init_db,
):
    with patch("sys.argv", ["safe_undo.py", "list"]):
        safe_undo.main()
        mock_run_list.assert_called_once()

    with patch("sys.argv", ["safe_undo.py", "rollback", "123"]):
        safe_undo.main()
        mock_rollback_transaction.assert_called_once_with(123, unittest.mock.ANY)

    with patch("sys.argv", ["safe_undo.py", "delete", "file.txt"]):
        safe_undo.main()
        mock_safe_delete.assert_called_once_with(
            "file.txt", unittest.mock.ANY, unittest.mock.ANY
        )

    with patch("sys.argv", ["safe_undo.py", "move", "src.txt", "dest.txt"]):
        safe_undo.main()
        mock_safe_move.assert_called_once_with(
            "src.txt", "dest.txt", unittest.mock.ANY, unittest.mock.ANY
        )
