import os
import re
import sys
from unittest.mock import patch

import pytest

# Add parent directory of this test file to sys.path so we can import share_safe
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import share_safe  # noqa: E402


def test_is_binary_text(tmp_path):
    file_path = tmp_path / "text.txt"
    file_path.write_text("This is clean text.")
    assert not share_safe.is_binary(str(file_path))


def test_is_binary_null_bytes(tmp_path):
    file_path = tmp_path / "binary.bin"
    file_path.write_bytes(b"some bytes\x00more bytes")
    assert share_safe.is_binary(str(file_path))


def test_is_binary_nonexistent():
    assert share_safe.is_binary("nonexistent_file_path.dat")


def test_redact_text():
    redactions = [(re.compile(r"\bfoo\b"), "BAR"), (re.compile(r"\b123\b"), "NUM")]
    content = "foo is 123 years old. foo is happy."
    modified, count = share_safe.redact_text(content, redactions)
    assert modified == "BAR is NUM years old. BAR is happy."
    assert count == 3


@patch("getpass.getuser", return_value="testuser")
@patch("os.path.expanduser", return_value="C:\\Users\\testuser")
def test_compile_redactors(mock_expand, mock_getuser):
    redactors = share_safe.compile_redactors(["secretword"])

    username_pattern = redactors[0][0]
    assert username_pattern.search("testuser") is not None
    assert username_pattern.search("TESTUSER") is not None

    home_pattern = redactors[1][0]
    assert home_pattern.search("C:\\Users\\testuser") is not None

    win_home_pattern = redactors[2][0]
    assert win_home_pattern.search("C:/Users/testuser") is not None

    ipv4_pattern = None
    for r in redactors:
        if "IP_REDACTED" in r[1]:
            ipv4_pattern = r[0]
            break
    assert ipv4_pattern is not None
    assert ipv4_pattern.search("192.168.1.1") is not None
    assert ipv4_pattern.search("256.300.999.0") is not None

    ipv6_pattern = None
    for r in redactors:
        if "IPv6_REDACTED" in r[1]:
            ipv6_pattern = r[0]
            break
    assert ipv6_pattern is not None
    assert ipv6_pattern.search("2001:db8:3333:4444:5555:6666:7777:8888") is not None

    token_pattern = None
    for r in redactors:
        if "TOKEN_REDACTED" in r[1]:
            token_pattern = r[0]
            break
    assert token_pattern is not None
    assert token_pattern.search("Authorization: Bearer my-secret-token") is not None

    key_pattern = None
    for r in redactors:
        if "[REDACTED]" in r[1]:
            key_pattern = r[0]
            break
    assert key_pattern is not None
    assert key_pattern.search("key = 'abcdefgh'") is not None
    assert key_pattern.search('password: "supersecret"') is not None

    custom_pattern = redactors[-1][0]
    assert custom_pattern.search("secretword") is not None
    assert custom_pattern.search("SECRETWORD") is not None


def test_main_source_not_exists(capsys):
    with patch("sys.argv", ["share_safe.py", "nonexistent_source", "dest_dir"]):
        with pytest.raises(SystemExit) as exc:
            share_safe.main()
        assert exc.value.code == 1
        captured = capsys.readouterr()
        assert "Source does not exist" in captured.err


def test_main_dest_exists(tmp_path, capsys):
    src = tmp_path / "src.txt"
    src.write_text("hello")
    dest = tmp_path / "dest.txt"
    dest.write_text("already exists")

    with patch("sys.argv", ["share_safe.py", str(src), str(dest)]):
        with pytest.raises(SystemExit) as exc:
            share_safe.main()
        assert exc.value.code == 1
        captured = capsys.readouterr()
        assert "Destination already exists" in captured.err


@patch("getpass.getuser", return_value="alice")
@patch("os.path.expanduser", return_value="C:\\Users\\alice")
def test_main_dry_run(mock_expand, mock_getuser, tmp_path, capsys):
    src = tmp_path / "src.txt"
    src.write_text("My username is alice and IP is 10.0.0.1.")
    dest = tmp_path / "dest.txt"

    with patch("sys.argv", ["share_safe.py", "-d", str(src), str(dest)]):
        share_safe.main()
        captured = capsys.readouterr()
        assert "[!] Running in DRY-RUN mode" in captured.out
        assert "flagged 2 redaction matches" in captured.out
        assert not os.path.exists(dest)


@patch("getpass.getuser", return_value="bob")
@patch("os.path.expanduser", return_value="C:\\Users\\bob")
def test_main_sanitize_file(mock_expand, mock_getuser, tmp_path):
    src = tmp_path / "src.txt"
    src.write_text("Hello bob at C:\\Users\\bob. Use key='secret1234'.")
    dest = tmp_path / "dest.txt"

    with patch("sys.argv", ["share_safe.py", str(src), str(dest)]):
        share_safe.main()
        assert os.path.exists(dest)
        dest_content = dest.read_text()
        assert "Hello [USER_REDACTED]" in dest_content
        assert "bob" not in dest_content
        assert "key: '[REDACTED]'" in dest_content


@patch("getpass.getuser", return_value="charlie")
@patch("os.path.expanduser", return_value="/home/charlie")
def test_main_sanitize_directory(mock_expand, mock_getuser, tmp_path):
    src_dir = tmp_path / "src_dir"
    os.makedirs(src_dir)
    dest_dir = tmp_path / "dest_dir"

    file1 = src_dir / "file1.txt"
    file1.write_text("Hello charlie, your IP is 192.168.1.50.")

    file2 = src_dir / "file2.bin"
    file2.write_bytes(b"\x00charlie")

    subdir = src_dir / "subdir"
    os.makedirs(subdir)
    file3 = subdir / "file3.txt"
    file3.write_text("Authorization: Bearer abcdef123456")

    with patch(
        "sys.argv", ["share_safe.py", "-c", "extra_kw", str(src_dir), str(dest_dir)]
    ):
        share_safe.main()

        dest_file1 = dest_dir / "file1.txt"
        assert dest_file1.exists()
        assert (
            dest_file1.read_text() == "Hello [USER_REDACTED], your IP is [IP_REDACTED]."
        )

        dest_file3 = dest_dir / "subdir" / "file3.txt"
        assert dest_file3.exists()
        assert "Authorization: [TOKEN_REDACTED]" in dest_file3.read_text()

        dest_file2 = dest_dir / "file2.bin"
        assert dest_file2.exists()
        assert dest_file2.read_bytes() == b"\x00charlie"
