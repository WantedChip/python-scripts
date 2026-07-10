"""Tests for Subtitle Fixer."""

import codecs
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

# pylint: disable=import-error, wrong-import-position
import subtitle_fixer  # noqa: E402


def test_timestamp_conversions() -> None:
    """Test converting timestamps to ms and vice versa."""
    assert subtitle_fixer.timestamp_to_ms("01:23:45,678") == 5025678
    assert subtitle_fixer.timestamp_to_ms("01:23:45.678") == 5025678
    assert subtitle_fixer.timestamp_to_ms("1:23:45.67") == 5025670
    assert subtitle_fixer.timestamp_to_ms("00:45.6") == 45600

    assert subtitle_fixer.ms_to_timestamp(5025678, "SRT") == "01:23:45,678"
    assert subtitle_fixer.ms_to_timestamp(5025678, "VTT") == "01:23:45.678"
    assert subtitle_fixer.ms_to_timestamp(5025670, "ASS") == "1:23:45.67"

    assert subtitle_fixer.ms_to_timestamp(-100, "SRT") == "00:00:00,000"


def test_detect_file_encoding(tmp_path: Path) -> None:
    """Test file encoding auto-detection."""
    utf8_path = tmp_path / "utf8.srt"
    latin1_path = tmp_path / "latin1.srt"
    utf8_sig_path = tmp_path / "utf8sig.srt"

    utf8_path.write_text("Hello", encoding="utf-8")
    latin1_path.write_text("Héllò", encoding="windows-1252")

    # Write UTF-8 with BOM
    with open(utf8_sig_path, "wb") as f:
        f.write(codecs.BOM_UTF8)
        f.write("Hello".encode("utf-8"))

    assert subtitle_fixer.detect_file_encoding(utf8_path) == "utf-8"
    assert subtitle_fixer.detect_file_encoding(latin1_path) == "windows-1252"
    assert subtitle_fixer.detect_file_encoding(utf8_sig_path) == "utf-8-sig"


def test_parse_srt() -> None:
    """Test parsing SRT text format."""
    content = (
        "1\n"
        "00:01:20,000 --> 00:01:23,000\n"
        "Hello World\n\n"
        "2\n"
        "00:01:25,500 --> 00:01:28,200\n"
        "Subtitle Line 2\n"
    )
    entries = subtitle_fixer.parse_srt(content)
    assert len(entries) == 2
    assert entries[0].index == 1
    assert entries[0].start_ms == 80000
    assert entries[0].end_ms == 83000
    assert entries[0].text == "Hello World"


def test_parse_vtt() -> None:
    """Test parsing WebVTT text format."""
    content = (
        "WEBVTT\n\n"
        "1\n"
        "00:01:20.000 --> 00:01:23.000\n"
        "Hello WebVTT\n\n"
        "00:01:25.500 --> 00:01:28.200\n"
        "Line 2 without index\n"
    )
    entries = subtitle_fixer.parse_vtt(content)
    assert len(entries) == 2
    assert entries[0].text == "Hello WebVTT"
    assert entries[1].text == "Line 2 without index"


def test_parse_ass() -> None:
    """Test parsing SSA/ASS text formats."""
    content = (
        "[Script Info]\n"
        "Title: Test ASS\n\n"
        "[Events]\n"
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, "
        "Effect, Text\n"
        "Dialogue: 0,0:01:20.00,0:01:23.00,Default,,0,0,0,,Hello {\\i1}ASS{\\i0}\n"
    )
    entries = subtitle_fixer.parse_ass(content)
    assert len(entries) == 1
    assert entries[0].text == "Hello ASS"
    assert entries[0].start_ms == 80000
    assert entries[0].end_ms == 83000


def test_parse_subtitle_file_formats(tmp_path: Path) -> None:
    """Test auto-detection parser fallback heuristic checks."""
    srt = tmp_path / "sub.srt"
    vtt = tmp_path / "sub.vtt"
    ass = tmp_path / "sub.ass"

    srt.write_text("1\n00:01:20,000 --> 00:01:23,000\nHello SRT\n", encoding="utf-8")
    vtt.write_text(
        "WEBVTT\n\n00:01:20.000 --> 00:01:23.000\nHello VTT\n", encoding="utf-8"
    )
    ass.write_text(
        "[Events]\nFormat: Start, End, Text\n"
        "Dialogue: 0:01:20.00,0:01:23.00,Hello ASS\n",
        encoding="utf-8",
    )

    assert subtitle_fixer.parse_subtitle_file(srt)[0].text == "Hello SRT"
    assert subtitle_fixer.parse_subtitle_file(vtt)[0].text == "Hello VTT"
    assert subtitle_fixer.parse_subtitle_file(ass)[0].text == "Hello ASS"


def test_write_subtitle_file(tmp_path: Path) -> None:
    """Test writing different file extensions."""
    entries = [subtitle_fixer.SubtitleEntry(1, 1000, 3000, "Line")]

    srt = tmp_path / "out.srt"
    vtt = tmp_path / "out.vtt"
    ass = tmp_path / "out.ass"
    txt = tmp_path / "out.txt"

    subtitle_fixer.write_subtitle_file(entries, srt)
    subtitle_fixer.write_subtitle_file(entries, vtt)
    subtitle_fixer.write_subtitle_file(entries, ass)
    subtitle_fixer.write_subtitle_file(entries, txt)

    assert "1" in srt.read_text(encoding="utf-8")
    assert "WEBVTT" in vtt.read_text(encoding="utf-8")
    assert "[Events]" in ass.read_text(encoding="utf-8")
    assert "1" in txt.read_text(encoding="utf-8")


def test_handle_shift() -> None:
    """Test timestamp shift operation."""
    entries = [subtitle_fixer.SubtitleEntry(1, 1000, 3000, "Text")]
    shifted = subtitle_fixer.handle_shift(entries, 500)
    assert shifted[0].start_ms == 1500
    assert shifted[0].end_ms == 3500

    shifted_back = subtitle_fixer.handle_shift(entries, -2000)
    assert shifted_back[0].start_ms == 0
    assert shifted_back[0].end_ms == 1000


def test_handle_dedup() -> None:
    """Test text overlap deduplication matching."""
    entries = [
        subtitle_fixer.SubtitleEntry(1, 1000, 3000, "Sub Title"),
        subtitle_fixer.SubtitleEntry(2, 1500, 2500, "Sub Title Line"),  # duplicate
        subtitle_fixer.SubtitleEntry(
            3, 4000, 6000, "Sub Title Line"
        ),  # non-overlapping
    ]
    # Similarity ratio: "Sub Title" vs "Sub Title Line" is around 0.8
    res = subtitle_fixer.handle_dedup(entries, 0.7)
    assert len(res) == 2
    assert res[0].text == "Sub Title"
    assert res[1].text == "Sub Title Line"
    assert res[1].start_ms == 4000


def test_main_cli_shift(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Test main function CLI arguments for shifting."""
    sub = tmp_path / "sub.srt"
    out = tmp_path / "out.srt"
    sub.write_text("1\n00:01:20,000 --> 00:01:23,000\nHello\n", encoding="utf-8")

    args = [
        "subtitle_fixer.py",
        "-i",
        str(sub),
        "-o",
        str(out),
        "shift",
        "-s",
        "1000",
    ]
    monkeypatch.setattr(sys, "argv", args)
    subtitle_fixer.main()

    assert out.exists()
    entries = subtitle_fixer.parse_subtitle_file(out)
    assert entries[0].start_ms == 81000


def test_main_cli_dedup(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Test main CLI deduplication execution."""
    sub = tmp_path / "sub.srt"
    out = tmp_path / "out.srt"
    sub.write_text(
        "1\n00:01:00,000 --> 00:01:03,000\nHello\n\n"
        "2\n00:01:01,000 --> 00:01:02,000\nHello\n",
        encoding="utf-8",
    )

    args = [
        "subtitle_fixer.py",
        "-i",
        str(sub),
        "-o",
        str(out),
        "dedup",
    ]
    monkeypatch.setattr(sys, "argv", args)
    subtitle_fixer.main()

    entries = subtitle_fixer.parse_subtitle_file(out)
    assert len(entries) == 1


def test_main_cli_repair_inplace(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Test running repair subcommand in-place."""
    sub = tmp_path / "sub.srt"
    sub.write_text("1\n00:01:20,000 --> 00:01:23,000\nHello\n", encoding="utf-8")

    args = [
        "subtitle_fixer.py",
        "-i",
        str(sub),
        "--in-place",
        "repair",
    ]
    monkeypatch.setattr(sys, "argv", args)
    subtitle_fixer.main()

    # Backup should exist
    assert (tmp_path / "sub.srt.bak").exists()


def test_main_cli_error_exits(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Test CLI exit codes on bad parameters."""
    sub = tmp_path / "sub.srt"
    sub.write_text("1\n00:01:20,000 --> 00:01:23,000\nHello\n", encoding="utf-8")

    # Missing output or in-place flags
    args = [
        "subtitle_fixer.py",
        "-i",
        str(sub),
        "convert",
    ]
    monkeypatch.setattr(sys, "argv", args)
    with pytest.raises(SystemExit) as exc:
        subtitle_fixer.main()
    assert exc.value.code == 1

    # Nonexistent input file
    args = [
        "subtitle_fixer.py",
        "-i",
        "nonexistent_sub_file.srt",
        "--in-place",
        "convert",
    ]
    monkeypatch.setattr(sys, "argv", args)
    with pytest.raises(SystemExit) as exc:
        subtitle_fixer.main()
    assert exc.value.code == 1
