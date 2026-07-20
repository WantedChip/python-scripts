import os
import sqlite3
import sys
from unittest.mock import ANY, MagicMock, patch

import pytest

# Add parent directory to path to import download_intent
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
import download_intent  # noqa: E402


def test_init_db(tmp_path):
    db_file = tmp_path / "test.db"
    download_intent.init_db(str(db_file))

    assert db_file.exists()

    # Check tables
    conn = sqlite3.connect(str(db_file))
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
    tables = [row[0] for row in cursor.fetchall()]
    assert "transactions" in tables
    assert "moves" in tables
    conn.close()


def test_classify_file():
    # Test invoices
    cat, score = download_intent.classify_file("invoice_123.pdf")
    assert cat == "invoices"
    assert score >= 0.5

    # Test installers
    cat, score = download_intent.classify_file("setup.exe")
    assert cat == "installers"
    assert score >= 0.5

    # Test screenshots
    cat, score = download_intent.classify_file("screenshot_today.png")
    assert cat == "screenshots"
    assert score >= 0.8

    # Test archives
    cat, score = download_intent.classify_file("backup.zip")
    assert cat == "archives"
    assert score >= 0.4

    # Test documents
    cat, score = download_intent.classify_file("resume.pdf")
    assert cat == "documents"
    assert score >= 0.5

    # Test junk
    cat, score = download_intent.classify_file("temp_log.tmp")
    assert cat == "junk"
    assert score >= 0.5

    # Test uncategorized / low confidence
    cat, score = download_intent.classify_file("random_file.xyz")
    assert cat == "uncategorized"


def test_move_file_recorded(tmp_path):
    db_file = tmp_path / "test.db"
    download_intent.init_db(str(db_file))

    # Setup files
    src_dir = tmp_path / "src"
    dest_dir = tmp_path / "dest"
    src_dir.mkdir()
    dest_dir.mkdir()

    src_file = src_dir / "invoice.pdf"
    src_file.write_text("dummy invoice content")

    conn = sqlite3.connect(str(db_file))

    success = download_intent.move_file_recorded(
        conn=conn,
        tx_id=1,
        src_path=str(src_file),
        dest_dir=str(dest_dir),
        category="invoices",
    )

    assert success is True
    # Verify file is moved
    assert not src_file.exists()
    dest_file = dest_dir / "invoices" / "invoice.pdf"
    assert dest_file.exists()

    # Check DB entry
    cursor = conn.cursor()
    cursor.execute("SELECT tx_id, original_path, new_path FROM moves")
    row = cursor.fetchone()
    assert row is not None
    assert row[0] == 1
    assert row[1] == os.path.abspath(str(src_file))
    assert row[2] == os.path.abspath(str(dest_file))

    # Test Collision (same filename)
    src_file2 = src_dir / "invoice.pdf"
    src_file2.write_text("second dummy content")

    success2 = download_intent.move_file_recorded(
        conn=conn,
        tx_id=1,
        src_path=str(src_file2),
        dest_dir=str(dest_dir),
        category="invoices",
    )
    assert success2 is True
    # Check that it got moved to a timestamped filename
    invoices_dir = dest_dir / "invoices"
    files = list(invoices_dir.glob("invoice_*.pdf"))
    assert len(files) == 1

    conn.close()


def test_move_file_recorded_exception(tmp_path):
    conn = MagicMock()
    # Mocking move to raise exception
    with patch("shutil.move", side_effect=Exception("Permission Denied")):
        success = download_intent.move_file_recorded(
            conn=conn,
            tx_id=1,
            src_path="dummy_src.pdf",
            dest_dir="dummy_dest",
            category="invoices",
        )
        assert success is False


def test_run_scan(tmp_path):
    db_file = tmp_path / "test.db"
    watch_dir = tmp_path / "watch"
    dest_dir = tmp_path / "dest"

    watch_dir.mkdir()
    dest_dir.mkdir()

    # Create some files in watch
    (watch_dir / "invoice.pdf").write_text("invoice")
    (watch_dir / "setup.exe").write_text("setup")
    (watch_dir / "other.xyz").write_text("other")
    (watch_dir / "pending.part").write_text("part file")  # Should be skipped

    # Dry Run first
    with patch("builtins.print"):
        download_intent.run_scan(
            watch_dir=str(watch_dir),
            dest_dir=str(dest_dir),
            db_path=str(db_file),
            dry_run=True,
        )
        # Check files were NOT moved
        assert (watch_dir / "invoice.pdf").exists()
        assert (watch_dir / "setup.exe").exists()
        assert (watch_dir / "other.xyz").exists()

        # Verify db initialized but no records inserted
        if db_file.exists():
            conn = sqlite3.connect(str(db_file))
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM transactions")
            assert cursor.fetchone()[0] == 0
            conn.close()

    # Real scan
    download_intent.run_scan(
        watch_dir=str(watch_dir),
        dest_dir=str(dest_dir),
        db_path=str(db_file),
        dry_run=False,
    )

    # Check moves
    assert not (watch_dir / "invoice.pdf").exists()
    assert not (watch_dir / "setup.exe").exists()
    assert (watch_dir / "other.xyz").exists()  # Uncategorized
    assert (watch_dir / "pending.part").exists()  # Skipped

    assert (dest_dir / "invoices" / "invoice.pdf").exists()
    assert (dest_dir / "installers" / "setup.exe").exists()

    # Check DB transaction
    conn = sqlite3.connect(str(db_file))
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM transactions")
    assert cursor.fetchone()[0] == 1
    cursor.execute("SELECT COUNT(*) FROM moves")
    assert cursor.fetchone()[0] == 2
    conn.close()


def test_run_scan_no_files_and_missing_dir(tmp_path):
    db_file = tmp_path / "test.db"

    # Test missing watch dir
    with pytest.raises(SystemExit) as exc:
        download_intent.run_scan(
            watch_dir="non_existent_watch_dir",
            dest_dir="dest",
            db_path=str(db_file),
            dry_run=False,
        )
    assert exc.value.code == 1

    # Test empty watch dir
    watch_dir = tmp_path / "empty_watch"
    watch_dir.mkdir()
    with patch("builtins.print") as mock_print:
        download_intent.run_scan(
            watch_dir=str(watch_dir),
            dest_dir="dest",
            db_path=str(db_file),
            dry_run=False,
        )
        mock_print.assert_any_call("No files to organize in watch directory.")


def test_run_scan_no_moves_confidence(tmp_path):
    db_file = tmp_path / "test.db"
    watch_dir = tmp_path / "watch"
    watch_dir.mkdir()
    # Create file that doesn't match rules (confidence < 0.3)
    (watch_dir / "readme.md").write_text("readme")

    with patch("builtins.print") as mock_print:
        download_intent.run_scan(
            watch_dir=str(watch_dir),
            dest_dir=str(tmp_path / "dest"),
            db_path=str(db_file),
            dry_run=False,
        )
        # Should delete transactions since moved_count == 0
        mock_print.assert_any_call(
            "No files met organizing confidence threshold. 0 files moved."
        )

        conn = sqlite3.connect(str(db_file))
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM transactions")
        assert cursor.fetchone()[0] == 0
        conn.close()


def test_run_undo(tmp_path):
    db_file = tmp_path / "test.db"
    watch_dir = tmp_path / "watch"
    dest_dir = tmp_path / "dest"
    watch_dir.mkdir()
    dest_dir.mkdir()

    # Create file, move it via scan
    (watch_dir / "invoice.pdf").write_text("invoice")
    download_intent.run_scan(
        watch_dir=str(watch_dir),
        dest_dir=str(dest_dir),
        db_path=str(db_file),
        dry_run=False,
    )

    assert not (watch_dir / "invoice.pdf").exists()
    assert (dest_dir / "invoices" / "invoice.pdf").exists()

    # Undo it
    download_intent.run_undo(str(db_file))

    # Should be back in watch_dir
    assert (watch_dir / "invoice.pdf").exists()
    assert not (dest_dir / "invoices" / "invoice.pdf").exists()

    # DB should be clean
    conn = sqlite3.connect(str(db_file))
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM transactions")
    assert cursor.fetchone()[0] == 0
    cursor.execute("SELECT COUNT(*) FROM moves")
    assert cursor.fetchone()[0] == 0
    conn.close()


def test_run_undo_no_db():
    with patch("builtins.print") as mock_print:
        download_intent.run_undo("non_existent_db.db")
        mock_print.assert_any_call("No transaction database found. Nothing to undo.")


def test_run_undo_no_transactions(tmp_path):
    db_file = tmp_path / "test.db"
    download_intent.init_db(str(db_file))
    with patch("builtins.print") as mock_print:
        download_intent.run_undo(str(db_file))
        mock_print.assert_any_call(
            "No transactions found in history database. Nothing to undo."
        )


def test_run_undo_missing_dest_file(tmp_path):
    db_file = tmp_path / "test.db"
    watch_dir = tmp_path / "watch"
    dest_dir = tmp_path / "dest"
    watch_dir.mkdir()
    dest_dir.mkdir()

    # Create file, move it via scan
    (watch_dir / "invoice.pdf").write_text("invoice")
    download_intent.run_scan(
        watch_dir=str(watch_dir),
        dest_dir=str(dest_dir),
        db_path=str(db_file),
        dry_run=False,
    )

    # Remove the moved file from dest
    os.remove(dest_dir / "invoices" / "invoice.pdf")

    with patch("builtins.print") as mock_print:
        download_intent.run_undo(str(db_file))
        # Warning about missing file
        any_warning = any(
            "Warning: File no longer exists" in call_args[0][0]
            for call_args in mock_print.call_args_list
        )
        assert any_warning is True

        # Original should still not exist
        assert not (watch_dir / "invoice.pdf").exists()


def test_run_watch():
    with patch("download_intent.run_scan") as mock_scan, patch(
        "time.sleep", side_effect=KeyboardInterrupt
    ):
        with pytest.raises(SystemExit) as exc:
            download_intent.run_watch("watch", "dest", "db", 5)
        assert exc.value.code == 0
        mock_scan.assert_called_once_with("watch", "dest", "db", dry_run=False)


def test_main():
    with patch(
        "sys.argv",
        ["download_intent.py", "scan", "-w", "watch", "-d", "dest", "--dry-run"],
    ), patch("download_intent.run_scan") as mock_scan:
        download_intent.main()
        mock_scan.assert_called_once_with("watch", "dest", ANY, True)

    with patch(
        "sys.argv",
        ["download_intent.py", "watch", "-w", "watch", "-d", "dest", "-i", "10"],
    ), patch("download_intent.run_watch") as mock_watch:
        download_intent.main()
        mock_watch.assert_called_once_with("watch", "dest", ANY, 10)

    with patch("sys.argv", ["download_intent.py", "undo"]), patch(
        "download_intent.run_undo"
    ) as mock_undo:
        download_intent.main()
        mock_undo.assert_called_once_with(ANY)
