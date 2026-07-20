import os
import sys
from unittest.mock import patch

# Add target directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
import ci_log_deduper  # noqa: E402


def test_normalize_error_line():
    # Hex addresses
    assert (
        ci_log_deduper.normalize_error_line("Error at 0x7f3b8c2a9b") == "Error at <HEX>"
    )
    # Standalone numbers
    assert (
        ci_log_deduper.normalize_error_line("Failed 42 times") == "Failed <NUM> times"
    )
    # Windows paths
    assert (
        ci_log_deduper.normalize_error_line(r"File C:\Path\To\File.txt not found")
        == "File <PATH> not found"
    )
    # Unix paths
    assert (
        ci_log_deduper.normalize_error_line("File /var/log/syslog not found")
        == "File <PATH> not found"
    )
    # Date and Time
    assert (
        ci_log_deduper.normalize_error_line("Crash on 2026-07-19 at 22:50:14")
        == "Crash on <DATE> at <TIME>"
    )
    # Mixed normalize
    assert (
        ci_log_deduper.normalize_error_line(
            "Exception 0xabc at 2026-07-19 in /usr/bin/python"
        )
        == "Exception <HEX> at <DATE> in <PATH>"
    )


def test_extract_failure_signature_nonexistent():
    res = ci_log_deduper.extract_failure_signature("nonexistent_file.log")
    assert res == "Unknown failure (file not found)"


def test_extract_failure_signature_python_traceback(tmp_path):
    log_content = """
Starting job...
Traceback (most recent call last):
  File "c:\\project\\main.py", line 10, in <module>
    run()
  File "c:\\project\\main.py", line 5, in run
    raise ValueError("invalid size 456 at 0xdeadbeef")
ValueError: invalid size 456 at 0xdeadbeef
Finished job with error.
"""
    log_file = tmp_path / "job_fail.log"
    log_file.write_text(log_content, encoding="utf-8")

    res = ci_log_deduper.extract_failure_signature(str(log_file))
    assert res == "ValueError: invalid size <NUM> at <HEX>"


def test_extract_failure_signature_generic_error(tmp_path):
    log_content = """
Starting setup...
WARNING: outdated package
FATAL: Database connection timed out on 2026-07-19
"""
    log_file = tmp_path / "db_fail.log"
    log_file.write_text(log_content, encoding="utf-8")

    res = ci_log_deduper.extract_failure_signature(str(log_file))
    assert res == "FATAL: Database connection timed out on <DATE>"


def test_extract_failure_signature_generic_error_filtered(tmp_path):
    log_content = """
Starting build...
npm ERR! code ELIFECYCLE
pip error: requirement not found
No actual stacktrace here.
"""
    log_file = tmp_path / "filtered_fail.log"
    log_file.write_text(log_content, encoding="utf-8")

    res = ci_log_deduper.extract_failure_signature(str(log_file))
    # Should not capture npm ERR! or pip error
    assert "no explicit trace found" in res


def test_extract_failure_signature_empty_fallback(tmp_path):
    log_file = tmp_path / "empty.log"
    log_file.write_text("Hello, everything is fine.\nSuccess.", encoding="utf-8")

    res = ci_log_deduper.extract_failure_signature(str(log_file))
    assert "no explicit trace found" in res


def test_main(tmp_path, capsys):
    log1 = tmp_path / "log1.log"
    log1.write_text(
        "Traceback (most recent call last):\n"
        '  File "a.py", line 1:\n'
        "    x()\n"
        "RuntimeError: error 1\n"
    )
    log2 = tmp_path / "log2.log"
    log2.write_text(
        "Traceback (most recent call last):\n"
        '  File "a.py", line 2:\n'
        "    x()\n"
        "RuntimeError: error 2\n"
    )
    log3 = tmp_path / "log3.log"
    log3.write_text("FATAL: Out of memory at 0x999\n")

    with patch("sys.argv", ["ci_log_deduper.py", str(log1), str(log2), str(log3)]):
        ci_log_deduper.main()

    captured = capsys.readouterr()
    assert "Log Files Checked: 3" in captured.out
    assert "Discovered 2 distinct root failure signatures" in captured.out
    assert "RuntimeError: error <NUM>" in captured.out
    assert "Occurrences: 2 log files" in captured.out
    assert "FATAL: Out of memory at <HEX>" in captured.out
    assert "Occurrences: 1 log files" in captured.out


def test_main_many_logs(tmp_path, capsys):
    logs = []
    for i in range(10):
        log = tmp_path / f"log_{i}.log"
        log.write_text("FATAL: Out of memory at 0x999\n")
        logs.append(str(log))

    with patch("sys.argv", ["ci_log_deduper.py"] + logs):
        ci_log_deduper.main()

    captured = capsys.readouterr()
    assert "and 5 more files." in captured.out
