"""Subtitle Fixer.

A CLI tool to shift timing, repair encoding, remove duplicate lines,
and convert subtitle formats (SRT ↔ VTT ↔ SSA/ASS) using pure standard library.
"""

import argparse
import codecs
import difflib
import logging
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

logger = logging.getLogger("subtitle_fixer")


@dataclass
class SubtitleEntry:
    """Represents a single subtitle line with timings."""

    index: Optional[int]
    start_ms: int
    end_ms: int
    text: str


def setup_logging(verbose: bool) -> None:
    """Configure logging.

    Args:
        verbose: If True, log level is set to DEBUG.
    """
    level = logging.DEBUG if verbose else logging.INFO
    handler = logging.StreamHandler(sys.stdout)
    formatter = logging.Formatter(
        "%(asctime)s - %(levelname)s - %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
    )
    handler.setFormatter(formatter)
    logger.setLevel(level)
    logger.addHandler(handler)
    logging.basicConfig(level=logging.WARNING, handlers=[handler])


def ms_to_timestamp(ms: int, format_type: str) -> str:
    """Convert milliseconds to timestamp string.

    Args:
        ms: Time in milliseconds.
        format_type: 'SRT', 'VTT', or 'ASS'.

    Returns:
        Formatted timestamp string.
    """
    ms = max(0, ms)
    hours = ms // 3600000
    ms %= 3600000
    minutes = ms // 60000
    ms %= 60000
    seconds = ms // 1000
    milliseconds = ms % 1000

    if format_type == "SRT":
        return f"{hours:02d}:{minutes:02d}:{seconds:02d},{milliseconds:03d}"
    if format_type == "VTT":
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}.{milliseconds:03d}"
    if format_type == "ASS":
        centiseconds = milliseconds // 10
        return f"{hours:01d}:{minutes:02d}:{seconds:02d}.{centiseconds:02d}"

    return ""


def timestamp_to_ms(ts: str) -> int:
    """Convert a timestamp string (SRT/VTT/ASS) to milliseconds.

    Args:
        ts: Timestamp string (e.g. '01:23:45,678' or '0:01:23.45').

    Returns:
        Milliseconds as integer.
    """
    ts = ts.strip().replace(",", ".")
    # Match ASS centiseconds (1:23:45.67) vs VTT/SRT milliseconds (01:23:45.678)
    parts = ts.split(":")
    if len(parts) == 3:
        h_str, m_str, s_str = parts
    elif len(parts) == 2:
        h_str, m_str, s_str = "0", parts[0], parts[1]
    else:
        raise ValueError(f"Invalid timestamp format: {ts}")

    hours = int(h_str)
    minutes = int(m_str)

    sec_parts = s_str.split(".")
    seconds = int(sec_parts[0])
    if len(sec_parts) > 1:
        ms_str = sec_parts[1]
        # Pad or truncate to 3 digits (milliseconds)
        if len(ms_str) == 2:
            ms = int(ms_str) * 10
        elif len(ms_str) == 1:
            ms = int(ms_str) * 100
        else:
            ms = int(ms_str[:3])
    else:
        ms = 0

    return (hours * 3600000) + (minutes * 60000) + (seconds * 1000) + ms


def detect_file_encoding(path: Path) -> str:
    """Detect file encoding using BOM sniffing and UTF-8 validation fallbacks.

    Args:
        path: Path to the target subtitle file.

    Returns:
        String name of the detected encoding.
    """
    # pylint: disable=too-many-return-statements

    # 1. BOM detection
    with open(path, "rb") as f:
        raw = f.read(4)

    if raw.startswith(codecs.BOM_UTF8):
        return "utf-8-sig"
    if raw.startswith(codecs.BOM_UTF16_LE):
        return "utf-16-le"
    if raw.startswith(codecs.BOM_UTF16_BE):
        return "utf-16-be"
    if raw.startswith(codecs.BOM_UTF32_LE):
        return "utf-32-le"
    if raw.startswith(codecs.BOM_UTF32_BE):
        return "utf-32-be"

    # 2. Try UTF-8 validation
    try:
        with open(path, "r", encoding="utf-8") as f:
            f.read()
        return "utf-8"
    except UnicodeDecodeError:
        pass

    # 3. Fallback to windows-1252 / latin-1 (common in subtitle downloads)
    return "windows-1252"


def parse_srt(content: str) -> List[SubtitleEntry]:
    """Parse SRT file content.

    Args:
        content: The text content of the SRT file.

    Returns:
        List of SubtitleEntry instances.
    """
    entries = []
    # Standard SRT blocks separated by blank lines
    blocks = re.split(r"\n\s*\n", content.strip())
    for block in blocks:
        lines = [line.strip() for line in block.split("\n") if line.strip()]
        if len(lines) >= 3:
            try:
                index = int(lines[0])
                time_line = lines[1]
                times = time_line.split("-->")
                if len(times) != 2:
                    continue
                start = timestamp_to_ms(times[0])
                end = timestamp_to_ms(times[1])
                text = "\n".join(lines[2:])
                entries.append(SubtitleEntry(index, start, end, text))
            except ValueError:
                # Skip malformed blocks
                continue
    return entries


def parse_vtt(content: str) -> List[SubtitleEntry]:
    """Parse WebVTT file content.

    Args:
        content: The text content of the WebVTT file.

    Returns:
        List of SubtitleEntry instances.
    """
    entries = []
    # Remove WEBVTT header and metadata lines
    lines = content.split("\n")
    cleaned_lines = []
    in_header = True
    for line in lines:
        if in_header:
            if "-->" in line:
                in_header = False
            elif line.strip() == "":
                continue
            else:
                continue
        cleaned_lines.append(line)

    # Rejoin and split by blocks
    blocks = re.split(r"\n\s*\n", "\n".join(cleaned_lines).strip())
    counter = 1
    for block in blocks:
        lines = [line.strip() for line in block.split("\n") if line.strip()]
        if len(lines) >= 2:
            time_line = lines[0]
            text_start_idx = 1
            # Check if first line is index or name
            if "-->" not in time_line and len(lines) >= 3:
                time_line = lines[1]
                text_start_idx = 2

            if "-->" in time_line:
                try:
                    times = time_line.split("-->")
                    start = timestamp_to_ms(times[0])
                    end = timestamp_to_ms(times[1])
                    text = "\n".join(lines[text_start_idx:])
                    entries.append(SubtitleEntry(counter, start, end, text))
                    counter += 1
                except ValueError:
                    continue
    return entries


def parse_ass(content: str) -> List[SubtitleEntry]:
    """Parse ASS/SSA subtitle events.

    Args:
        content: The ASS/SSA text content.

    Returns:
        List of SubtitleEntry instances.
    """
    entries = []
    lines = content.split("\n")
    in_events = False
    format_indices = {}
    counter = 1

    for line in lines:
        line_strip = line.strip()
        if line_strip == "[Events]":
            in_events = True
            continue
        if in_events:
            if line_strip.startswith("[") and line_strip.endswith("]"):
                break  # dynamic section change
            if line_strip.startswith("Format:"):
                fields = [f.strip() for f in line_strip[7:].split(",")]
                format_indices = {field: idx for idx, field in enumerate(fields)}
            elif line_strip.startswith("Dialogue:"):
                # Split dialouge values
                dialogue_vals = [
                    v.strip()
                    for v in line_strip[9:].split(",", len(format_indices) - 1)
                ]
                if len(dialogue_vals) >= len(format_indices):
                    try:
                        start_str = dialogue_vals[format_indices["Start"]]
                        end_str = dialogue_vals[format_indices["End"]]
                        text = dialogue_vals[format_indices["Text"]]
                        # Remove styling cues (e.g. {\i1} or {\pos(10,20)})
                        text_clean = re.sub(r"\{.*?\}", "", text)
                        entries.append(
                            SubtitleEntry(
                                counter,
                                timestamp_to_ms(start_str),
                                timestamp_to_ms(end_str),
                                text_clean,
                            )
                        )
                        counter += 1
                    except (KeyError, ValueError):
                        continue
    return entries


def parse_subtitle_file(path: Path) -> List[SubtitleEntry]:
    """Parse subtitle file auto-detecting the format.

    Args:
        path: Path to the subtitle file.

    Returns:
        List of SubtitleEntry records.
    """
    encoding = detect_file_encoding(path)
    logger.info("Detected encoding: %s", encoding)
    with open(path, "r", encoding=encoding) as f:
        content = f.read()

    suffix = path.suffix.lower()
    if suffix == ".srt":
        return parse_srt(content)
    if suffix == ".vtt":
        return parse_vtt(content)
    if suffix in [".ssa", ".ass"]:
        return parse_ass(content)

    # Fallback heuristic checks
    if "[Events]" in content:
        return parse_ass(content)
    if "WEBVTT" in content:
        return parse_vtt(content)
    return parse_srt(content)


def write_srt(entries: List[SubtitleEntry]) -> str:
    """Format entries as SRT string."""
    lines = []
    for idx, entry in enumerate(entries, 1):
        start = ms_to_timestamp(entry.start_ms, "SRT")
        end = ms_to_timestamp(entry.end_ms, "SRT")
        lines.append(f"{idx}\n{start} --> {end}\n{entry.text}\n")
    return "\n".join(lines)


def write_vtt(entries: List[SubtitleEntry]) -> str:
    """Format entries as WebVTT string."""
    lines = ["WEBVTT\n"]
    for idx, entry in enumerate(entries, 1):
        start = ms_to_timestamp(entry.start_ms, "VTT")
        end = ms_to_timestamp(entry.end_ms, "VTT")
        lines.append(f"{idx}\n{start} --> {end}\n{entry.text}\n")
    return "\n".join(lines)


def write_ass(entries: List[SubtitleEntry]) -> str:
    """Format entries as basic ASS string."""
    header = (
        "[Script Info]\n"
        "Title: Converted Subtitles\n"
        "ScriptType: v4.00+\n"
        "Collisions: Normal\n\n"
        "[V4+ Styles]\n"
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, "
        "OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, "
        "ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, "
        "Alignment, MarginL, MarginR, MarginV, Encoding\n"
        "Style: Default,Arial,20,&H00FFFFFF,&H000000FF,&H00000000,"
        "&H00000000,0,0,0,0,100,100,0,0,1,2,2,2,10,10,10,1\n\n"
        "[Events]\n"
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, "
        "Effect, Text\n"
    )
    events = []
    for entry in entries:
        start = ms_to_timestamp(entry.start_ms, "ASS")
        end = ms_to_timestamp(entry.end_ms, "ASS")
        # ASS dialogue lines replace newlines with \N
        text_clean = entry.text.replace("\n", "\\N")
        events.append(f"Dialogue: 0,{start},{end},Default,,0,0,0,,{text_clean}")
    return header + "\n".join(events) + "\n"


def write_subtitle_file(entries: List[SubtitleEntry], path: Path) -> None:
    """Serialize and save subtitles to disk.

    Args:
        entries: List of SubtitleEntry objects.
        path: Target file output path.
    """
    suffix = path.suffix.lower()
    if suffix == ".srt":
        content = write_srt(entries)
    elif suffix == ".vtt":
        content = write_vtt(entries)
    elif suffix in [".ssa", ".ass"]:
        content = write_ass(entries)
    else:
        # Default to SRT
        content = write_srt(entries)

    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    logger.info("Saved %d entries to %s", len(entries), path.as_posix())


def handle_shift(entries: List[SubtitleEntry], shift_ms: int) -> List[SubtitleEntry]:
    """Shift all entry timings.

    Args:
        entries: The list of subtitle lines.
        shift_ms: Milliseconds to add/subtract.

    Returns:
        Shifted list of entries.
    """
    shifted = []
    for entry in entries:
        start = max(0, entry.start_ms + shift_ms)
        end = max(0, entry.end_ms + shift_ms)
        shifted.append(SubtitleEntry(entry.index, start, end, entry.text))
    logger.info("Shifted %d lines by %d ms.", len(entries), shift_ms)
    return shifted


def handle_dedup(entries: List[SubtitleEntry], threshold: float) -> List[SubtitleEntry]:
    """Remove duplicate overlapping subtitle lines by string similarity ratio.

    Args:
        entries: The list of subtitle lines.
        threshold: Similary index threshold (0.0 to 1.0).

    Returns:
        Deduplicated list of entries.
    """
    deduped: List[SubtitleEntry] = []
    removed_count = 0
    for entry in entries:
        duplicate = False
        # Check against previously accepted entries
        for prev in deduped:
            # Overlap check
            overlap = not (
                entry.end_ms <= prev.start_ms or entry.start_ms >= prev.end_ms
            )
            if overlap:
                # Text similarity ratio
                ratio = difflib.SequenceMatcher(None, entry.text, prev.text).ratio()
                if ratio >= threshold:
                    duplicate = True
                    removed_count += 1
                    logger.debug(
                        "Removing duplicate line: '%s' (matches '%s' ratio %.2f)",
                        entry.text,
                        prev.text,
                        ratio,
                    )
                    break
        if not duplicate:
            deduped.append(entry)
    logger.info("Deduplication removed %d duplicate lines.", removed_count)
    return deduped


def main() -> None:
    """CLI execution entry point."""
    parser = argparse.ArgumentParser(
        description=(
            "Subtitle Fixer — shift timing, repair encoding, remove "
            "duplicates, and convert formats."
        )
    )
    parser.add_argument(
        "-i", "--input", required=True, type=Path, help="Input subtitle file."
    )
    parser.add_argument("-o", "--output", type=Path, help="Output subtitle file.")
    parser.add_argument(
        "--in-place",
        action="store_true",
        help="Overwrite original file (creates backup).",
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true", help="Enable verbose debug logging."
    )

    subparsers = parser.add_subparsers(
        dest="command", required=True, help="Subcommands"
    )

    # Shift Subcommand
    shift_parser = subparsers.add_parser("shift", help="Shift timing timestamps.")
    shift_parser.add_argument(
        "-s",
        "--shift",
        required=True,
        help=(
            "Time value in ms (e.g. '1000' or '-500') or "
            "ASS/SRT format 'HH:MM:SS,mmm'."
        ),
    )

    # Convert Subcommand
    subparsers.add_parser(
        "convert", help="Convert format (formats determined by suffix)."
    )

    # Dedup Subcommand
    dedup_parser = subparsers.add_parser("dedup", help="Deduplicate overlapping lines.")
    dedup_parser.add_argument(
        "-t",
        "--threshold",
        type=float,
        default=0.85,
        help="String similarity threshold (0.0 - 1.0).",
    )

    # Repair Subcommand
    repair_parser = subparsers.add_parser(
        "repair", help="Run encoding fixes and deduplication in sequence."
    )
    repair_parser.add_argument(
        "-t",
        "--threshold",
        type=float,
        default=0.85,
        help="Deduplicate similarity threshold.",
    )

    args = parser.parse_args()
    setup_logging(args.verbose)

    if not args.input.exists():
        logger.error("Input file does not exist: %s", args.input.as_posix())
        sys.exit(1)

    # Determine out path
    if args.in_place:
        out_path = args.input
        # Backup original
        backup_path = args.input.with_suffix(args.input.suffix + ".bak")
        try:
            backup_path.write_bytes(args.input.read_bytes())
            logger.info("Created backup: %s", backup_path.name)
        except Exception as err:  # pylint: disable=broad-exception-caught
            logger.error("Failed to create file backup: %s", err)
            sys.exit(1)

    elif args.output:
        out_path = args.output
    else:
        logger.error("Must specify --output or --in-place.")
        sys.exit(1)

    try:
        # Load and parse entries (encoding auto-detected)
        entries = parse_subtitle_file(args.input)
        logger.info("Loaded %d subtitle entries.", len(entries))

        if args.command == "shift":
            try:
                shift_ms = int(args.shift)
            except ValueError:
                # Try parsing timestamp format
                shift_ms = timestamp_to_ms(args.shift)
            entries = handle_shift(entries, shift_ms)
        elif args.command == "dedup":
            entries = handle_dedup(entries, args.threshold)
        elif args.command == "repair":
            entries = handle_dedup(entries, args.threshold)

        # Write output file (format determined by suffix of output path)
        write_subtitle_file(entries, out_path)

    except Exception as err:  # pylint: disable=broad-exception-caught
        logger.error("Error: %s", err)
        sys.exit(1)


if __name__ == "__main__":
    main()
