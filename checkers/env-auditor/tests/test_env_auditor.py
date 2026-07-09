"""Tests for env_auditor.py."""

# pylint: disable=wrong-import-position,import-error,missing-class-docstring
# pylint: disable=missing-function-docstring,unused-import
import sys
import pytest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from env_auditor import (  # noqa: E402
    audit,
    parse_env_file,
    scan_source_for_usage,
    parse_docker_compose_env_vars,
    find_docker_compose_files,
    print_report,
    main,
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


# ---------------------------------------------------------------------------
# Additional coverage tests
# ---------------------------------------------------------------------------
def test_parse_env_file_failure() -> None:
    """Test parse_env_file with non-existent file path exiting 1."""
    with pytest.raises(SystemExit) as exc_info:
        parse_env_file("nonexistent_env_file_123")
    assert exc_info.value.code == 1


def test_parse_docker_compose_env_vars(tmp_path: Path) -> None:
    """Test extraction of env vars from docker compose configurations."""
    # 1. Valid docker file
    compose = tmp_path / "docker-compose.yml"
    compose.write_text(
        "version: '3'\n"
        "services:\n"
        "  web:\n"
        "    environment:\n"
        "      - PORT=8080\n"
        "      - DB_URL=postgresql://${DB_USER}:${DB_PASS}@localhost/db\n"
        "      - TEMP_VAR: 123\n"
    )
    vars_found = parse_docker_compose_env_vars([str(compose)])
    assert "PORT" in vars_found
    assert "DB_USER" in vars_found
    assert "DB_PASS" in vars_found
    assert "TEMP_VAR" in vars_found

    # 2. Missing/unreadable file should log warning and continue
    vars_missing = parse_docker_compose_env_vars(["nonexistent_compose_file_123.yml"])
    assert vars_missing == set()


def test_find_docker_compose_files(tmp_path: Path) -> None:
    """Test discovery of docker compose files by pattern."""
    d1 = tmp_path / "docker-compose.yml"
    d1.touch()
    d2 = tmp_path / "compose.yaml"
    d2.touch()
    not_d = tmp_path / "other.yml"
    not_d.touch()
    
    files = find_docker_compose_files(str(tmp_path))
    basenames = [Path(f).name for f in files]
    assert "docker-compose.yml" in basenames
    assert "compose.yaml" in basenames
    assert "other.yml" not in basenames


def test_print_report(capsys: pytest.CaptureFixture[str]) -> None:
    """Test print_report helper formatting."""
    from env_auditor import AuditResult
    res = AuditResult(
        undocumented=["UNDOC"],
        missing_locally=["MISSING"],
        unused=["UNUSED"],
        unknown=["UNKNOWN"],
        docker_declared=["DOCKER_VAR"]
    )
    print_report(res, ".env", ".env.example")
    captured = capsys.readouterr()
    assert ".env Audit Report" in captured.out
    assert "UNDOC" in captured.out
    assert "MISSING" in captured.out
    assert "UNUSED" in captured.out
    assert "UNKNOWN" in captured.out
    assert "DOCKER_VAR" in captured.out


def test_main_cli_execution(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """Test main function execution and failure exit codes."""
    # 1. Nonexistent .env file exits 1
    with pytest.raises(SystemExit) as exc_info:
        main(["--env", "nonexistent_env_file_123"])
    assert exc_info.value.code == 1

    # 2. Nonexistent source dir exits 1
    env = tmp_path / ".env"
    env.touch()
    with pytest.raises(SystemExit) as exc_info:
        main(["--env", str(env), "--source", "nonexistent_source_dir_123"])
    assert exc_info.value.code == 1

    # 3. Clean audit returns successfully
    example = tmp_path / ".env.example"
    example.touch()
    main(["--env", str(env), "--example", str(example), "--source", str(tmp_path)])
    
    # 4. Audit with issues exits 1 when --fail-on-issues is provided
    env.write_text("SOME_VAR=123\n")
    with pytest.raises(SystemExit) as exc_info:
        main([
            "--env", str(env),
            "--example", str(example),
            "--source", str(tmp_path),
            "--fail-on-issues"
        ])
    assert exc_info.value.code == 1
