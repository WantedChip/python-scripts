"""Tests for SQLite Database Inspector."""

import json
import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

# pylint: disable=import-error, wrong-import-position
import sqlite_inspector  # noqa: E402


@pytest.fixture(name="test_db")
def fixture_test_db(tmp_path: Path) -> Path:
    """Create a temporary SQLite database with schema issues."""
    db_path = tmp_path / "test.db"
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # 1. Table users (Well-formed, PK, Index)
    cursor.execute("CREATE TABLE users (id INTEGER PRIMARY KEY, name TEXT, email TEXT)")
    cursor.execute("CREATE INDEX idx_users_email ON users(email)")

    # Insert data (some duplicates and nulls)
    cursor.execute("INSERT INTO users VALUES (1, 'Alice', 'alice@test.com')")
    cursor.execute("INSERT INTO users VALUES (2, 'Bob', NULL)")
    cursor.execute(
        "INSERT INTO users VALUES (3, 'Alice', 'alice@test.com')"
    )  # Duplicate name/email but distinct PK

    # 2. Table posts (Unindexed FK)
    cursor.execute(
        "CREATE TABLE posts (id INTEGER PRIMARY KEY, user_id INTEGER, title TEXT, "
        "FOREIGN KEY(user_id) REFERENCES users(id))"
    )

    # 3. Table settings (No Primary Key, Duplicate Rows)
    cursor.execute("CREATE TABLE settings (key TEXT, val TEXT)")
    cursor.execute("INSERT INTO settings VALUES ('theme', 'dark')")
    cursor.execute(
        "INSERT INTO settings VALUES ('theme', 'dark')"
    )  # Exact duplicate row

    # 4. Table profiles (Redundant Index)
    cursor.execute(
        "CREATE TABLE profiles (id INTEGER PRIMARY KEY, user_id INTEGER, bio TEXT)"
    )
    cursor.execute("CREATE INDEX idx_prof_user ON profiles(user_id)")
    cursor.execute(
        "CREATE INDEX idx_prof_user_bio ON profiles(user_id, bio)"
    )  # idx_prof_user is redundant prefix

    # 5. Table attachments (FK Type Mismatch)
    cursor.execute(
        "CREATE TABLE attachments (id INTEGER PRIMARY KEY, "
        "post_id TEXT, file_path TEXT, "
        "FOREIGN KEY(post_id) REFERENCES posts(id))"
    )  # post_id is TEXT locally, but INTEGER in posts

    conn.commit()
    conn.close()
    return db_path


def test_inspect_db(test_db: Path) -> None:
    """Test entire database audit inspector on sample schema."""
    report = sqlite_inspector.inspect_db(test_db)

    assert report.sqlite_version != ""
    assert report.journal_mode != ""
    assert report.db_size_bytes > 0

    tables = {t.name: t for t in report.tables}
    assert "users" in tables
    assert "posts" in tables
    assert "settings" in tables

    # Row counts
    assert tables["users"].row_count == 3
    assert tables["settings"].row_count == 2

    # Null check
    users_cols = {c.name: c for c in tables["users"].columns}
    assert users_cols["email"].null_percentage == 33.33

    # Exact duplicates check
    assert tables["settings"].duplicate_rows == 1

    # Issues audit checks
    issues_by_type: dict[str, list[sqlite_inspector.SchemaIssue]] = {}
    for issue in report.issues:
        issues_by_type.setdefault(issue.issue_type, []).append(issue)

    assert "NO_PK" in issues_by_type
    assert issues_by_type["NO_PK"][0].table == "settings"

    assert "UNINDEXED_FK" in issues_by_type
    assert issues_by_type["UNINDEXED_FK"][0].table == "posts"

    assert "REDUNDANT_INDEX" in issues_by_type
    assert issues_by_type["REDUNDANT_INDEX"][0].table == "profiles"

    assert "FK_TYPE_MISMATCH" in issues_by_type
    assert issues_by_type["FK_TYPE_MISMATCH"][0].table == "attachments"


def test_print_terminal_report(test_db: Path) -> None:
    """Test console summary printing logic doesn't throw errors."""
    report = sqlite_inspector.inspect_db(test_db)
    # Confirm no crashes during console output
    sqlite_inspector.print_terminal_report(report)


def test_main_cli_health_audit(
    test_db: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Test main CLI entry point runs and writes JSON output correctly."""
    out_json = tmp_path / "out.json"
    args = ["sqlite_inspector.py", "-i", str(test_db), "-o", str(out_json)]
    monkeypatch.setattr(sys, "argv", args)

    sqlite_inspector.main()

    assert out_json.exists()
    saved = json.loads(out_json.read_text(encoding="utf-8"))
    assert "sqlite_version" in saved
    assert len(saved["tables"]) > 0


def test_main_cli_missing_db(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test CLI behavior when target database file doesn't exist."""
    args = ["sqlite_inspector.py", "-i", "nonexistent.db"]
    monkeypatch.setattr(sys, "argv", args)

    with pytest.raises(SystemExit) as exc:
        sqlite_inspector.main()
    assert exc.value.code == 1


def test_main_cli_corrupted_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Test CLI behavior when database connection fails or is corrupted."""
    bad_db = tmp_path / "corrupted.db"
    bad_db.write_text("invalid sqlite signature data", encoding="utf-8")

    args = ["sqlite_inspector.py", "-i", str(bad_db)]
    monkeypatch.setattr(sys, "argv", args)

    with pytest.raises(SystemExit) as exc:
        sqlite_inspector.main()
    assert exc.value.code == 1
