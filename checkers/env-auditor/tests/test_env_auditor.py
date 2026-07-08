"""Tests for env_auditor.py."""

# pylint: disable=wrong-import-position,import-error,missing-class-docstring
# pylint: disable=missing-function-docstring,unused-import
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from env_auditor import (  # noqa: E402
    audit,
    parse_env_file,
    scan_source_for_usage,
)


# ---------------------------------------------------------------------------
# parse_env_file
# ---------------------------------------------------------------------------
class TestParseEnvFile:
    def test_basic_parsing(self, tmp_path: Path) -> None:
        env = tmp_path / ".env"
        env.write_text("DB_HOST=localhost\nDB_PORT=5432\n")
        result = parse_env_file(str(env))
        assert "DB_HOST" in result
        assert "DB_PORT" in result
        # Values must be redacted
        assert result["DB_HOST"] == "<REDACTED>"

    def test_comments_ignored(self, tmp_path: Path) -> None:
        env = tmp_path / ".env"
        env.write_text("# This is a comment\nDB_HOST=localhost\n")
        result = parse_env_file(str(env))
        assert "DB_HOST" in result
        assert len(result) == 1

    def test_export_prefix_handled(self, tmp_path: Path) -> None:
        env = tmp_path / ".env"
        env.write_text("export SECRET_KEY=abc123\n")
        result = parse_env_file(str(env))
        assert "SECRET_KEY" in result

    def test_empty_lines_ignored(self, tmp_path: Path) -> None:
        env = tmp_path / ".env"
        env.write_text("\nDB_HOST=localhost\n\n\nDB_PORT=5432\n")
        result = parse_env_file(str(env))
        assert len(result) == 2

    def test_invalid_key_ignored(self, tmp_path: Path) -> None:
        env = tmp_path / ".env"
        env.write_text("123INVALID=value\nVALID_KEY=value\n")
        result = parse_env_file(str(env))
        assert "VALID_KEY" in result
        assert "123INVALID" not in result


# ---------------------------------------------------------------------------
# scan_source_for_usage
# ---------------------------------------------------------------------------
class TestScanSourceForUsage:
    def test_os_environ_get(self, tmp_path: Path) -> None:
        src = tmp_path / "app.py"
        src.write_text("db = os.environ.get('DB_HOST', 'localhost')\n")
        result = scan_source_for_usage(str(tmp_path), (".py",), ())
        assert "DB_HOST" in result

    def test_os_getenv(self, tmp_path: Path) -> None:
        src = tmp_path / "app.py"
        src.write_text('secret = os.getenv("SECRET_KEY")\n')
        result = scan_source_for_usage(str(tmp_path), (".py",), ())
        assert "SECRET_KEY" in result

    def test_process_env(self, tmp_path: Path) -> None:
        src = tmp_path / "app.js"
        src.write_text("const key = process.env.API_KEY;\n")
        result = scan_source_for_usage(str(tmp_path), (".js",), ())
        assert "API_KEY" in result

    def test_excluded_dirs_skipped(self, tmp_path: Path) -> None:
        venv = tmp_path / "venv"
        venv.mkdir()
        src = venv / "app.py"
        src.write_text('x = os.getenv("SECRET_KEY")\n')
        result = scan_source_for_usage(str(tmp_path), (".py",), ("venv",))
        assert "SECRET_KEY" not in result


# ---------------------------------------------------------------------------
# audit (integration)
# ---------------------------------------------------------------------------
class TestAudit:
    def test_missing_locally(self, tmp_path: Path) -> None:
        env = tmp_path / ".env"
        env.write_text("DB_HOST=localhost\n")
        example = tmp_path / ".env.example"
        example.write_text("DB_HOST=\nSECRET_KEY=\n")
        src = tmp_path / "app.py"
        src.write_text("")

        result = audit(
            env_path=str(env),
            example_path=str(example),
            source_root=str(tmp_path),
            source_extensions=(".py",),
            exclude_dirs=(),
            docker_files=[],
        )
        assert "SECRET_KEY" in result.missing_locally

    def test_undocumented_var(self, tmp_path: Path) -> None:
        env = tmp_path / ".env"
        env.write_text("DB_HOST=localhost\nSECRET=abc\n")
        example = tmp_path / ".env.example"
        example.write_text("DB_HOST=\n")
        src = tmp_path / "app.py"
        src.write_text("")

        result = audit(
            env_path=str(env),
            example_path=str(example),
            source_root=str(tmp_path),
            source_extensions=(".py",),
            exclude_dirs=(),
            docker_files=[],
        )
        assert "SECRET" in result.undocumented

    def test_unused_var(self, tmp_path: Path) -> None:
        env = tmp_path / ".env"
        env.write_text("UNUSED_VAR=foo\n")
        example = tmp_path / ".env.example"
        example.write_text("UNUSED_VAR=\n")
        src = tmp_path / "app.py"
        src.write_text("# no env usage\n")

        result = audit(
            env_path=str(env),
            example_path=str(example),
            source_root=str(tmp_path),
            source_extensions=(".py",),
            exclude_dirs=(),
            docker_files=[],
        )
        assert "UNUSED_VAR" in result.unused

    def test_unknown_var_used_in_source(self, tmp_path: Path) -> None:
        env = tmp_path / ".env"
        env.write_text("DB_HOST=localhost\n")
        example = tmp_path / ".env.example"
        example.write_text("DB_HOST=\n")
        src = tmp_path / "app.py"
        src.write_text('x = os.getenv("MYSTERY_VAR")\n')

        result = audit(
            env_path=str(env),
            example_path=str(example),
            source_root=str(tmp_path),
            source_extensions=(".py",),
            exclude_dirs=(),
            docker_files=[],
        )
        assert "MYSTERY_VAR" in result.unknown
