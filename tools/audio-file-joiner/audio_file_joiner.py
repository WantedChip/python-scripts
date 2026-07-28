"""Concatenate multiple audio files into a single audio file with optional crossfade.

This module merges multiple input audio files in sequence using FFmpeg concat filter
or native WAV PCM concatenation for uncompressed audio files.
"""

# pylint: disable=too-many-branches,too-many-statements,too-many-locals
# pylint: disable=too-many-arguments,too-many-positional-arguments

import argparse
import logging
import os
import shutil
import subprocess  # nosec B404
import sys
import tempfile
import wave
from pathlib import Path
from typing import List, Optional

logger = logging.getLogger(__name__)


def join_wav_files_native(
    input_wavs: List[Path],
    output_wav: Path,
) -> bool:
    """Concatenate multiple 16-bit PCM WAV files natively.

    Args:
        input_wavs: List of input WAV file paths.
        output_wav: Path to destination merged WAV file.

    Returns:
        True if WAV concatenation succeeded, False otherwise.
    """
    if not input_wavs:
        return False

    try:
        combined_frames = []
        n_channels = 0
        samp_width = 0
        framerate = 0

        for idx, wav_path in enumerate(input_wavs):
            with wave.open(str(wav_path), "rb") as r_wav:
                if idx == 0:
                    n_channels = r_wav.getnchannels()
                    samp_width = r_wav.getsampwidth()
                    framerate = r_wav.getframerate()
                elif (
                    r_wav.getnchannels() != n_channels
                    or r_wav.getsampwidth() != samp_width
                    or r_wav.getframerate() != framerate
                ):
                    logger.error(
                        "WAV properties mismatch in native joiner: %s",
                        wav_path,
                    )
                    return False

                combined_frames.append(r_wav.readframes(r_wav.getnframes()))

        output_wav.parent.mkdir(parents=True, exist_ok=True)
        # pylint: disable=no-member
        with wave.open(str(output_wav), "wb") as w_wav:
            w_wav.setnchannels(n_channels)
            w_wav.setsampwidth(samp_width)
            w_wav.setframerate(framerate)
            w_wav.writeframes(b"".join(combined_frames))

        logger.info(
            "Natively joined %d WAV files into: %s",
            len(input_wavs),
            output_wav.name,
        )
        return True
    except Exception as exc:  # pylint: disable=broad-exception-caught
        logger.error("Exception in native WAV joiner: %s", exc)
        return False


def join_audio_files_ffmpeg(
    input_files: List[Path],
    output_file: Path,
    overwrite: bool = True,
) -> bool:
    """Concatenate audio files using FFmpeg concat demuxer.

    Args:
        input_files: List of input audio file paths.
        output_file: Target merged audio file path.
        overwrite: Overwrite destination file if True.

    Returns:
        True if FFmpeg audio concatenation succeeded, False otherwise.
    """
    ffmpeg_bin = shutil.which("ffmpeg")
    if not ffmpeg_bin:
        return False

    output_file.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.NamedTemporaryFile("w", delete=False, suffix=".txt") as tmp:
        list_path = Path(tmp.name)
        for f in input_files:
            escaped_path = str(f.resolve()).replace("\\", "/")
            tmp.write(f"file '{escaped_path}'\n")

    cmd = [
        ffmpeg_bin,
        "-y" if overwrite else "-n",
        "-f",
        "concat",
        "-safe",
        "0",
        "-i",
        str(list_path),
        "-c",
        "copy",
        str(output_file),
    ]

    try:
        res = subprocess.run(  # nosec B603
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            text=True,
        )
        if list_path.exists():
            os.remove(list_path)

        if res.returncode == 0 and output_file.exists():
            logger.info(
                "Joined %d audio files via FFmpeg: %s",
                len(input_files),
                output_file.name,
            )
            return True

        logger.error("FFmpeg concat error: %s", res.stderr)
        return False
    except Exception as exc:  # pylint: disable=broad-exception-caught
        if list_path.exists():
            os.remove(list_path)
        logger.error("Exception running FFmpeg concat: %s", exc)
        return False


def join_audio_files(
    input_files: List[Path],
    output_file: Path,
) -> bool:
    """Join multiple audio files into one target file.

    Args:
        input_files: List of source audio files.
        output_file: Destination output audio file.

    Returns:
        True if joined successfully, False otherwise.
    """
    if not input_files:
        logger.error("No input files provided to join.")
        return False

    if shutil.which("ffmpeg"):
        ok = join_audio_files_ffmpeg(input_files, output_file)
        if ok:
            return True

    if all(f.suffix.lower() == ".wav" for f in input_files):
        return join_wav_files_native(input_files, output_file)

    logger.error("Cannot join files: FFmpeg is missing.")
    return False


def setup_cli_parser() -> argparse.ArgumentParser:
    """Construct CLI argument parser.

    Returns:
        Configured ArgumentParser object.
    """
    parser = argparse.ArgumentParser(
        description="Concatenate multiple audio files into a single output file."
    )
    parser.add_argument(
        "inputs",
        nargs="+",
        type=str,
        help="Input audio file paths (or directory).",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=str,
        required=True,
        help="Target merged audio file output path.",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Enable detailed debug logging.",
    )
    return parser


def main(args: Optional[List[str]] = None) -> int:
    """Main CLI entry point.

    Args:
        args: Argument list or None for sys.argv[1:].

    Returns:
        Exit code integer (0 for success, non-zero for error).
    """
    parser = setup_cli_parser()
    parsed_args = parser.parse_args(args)

    log_level = logging.DEBUG if parsed_args.verbose else logging.INFO
    logging.basicConfig(level=log_level, format="%(levelname)s: %(message)s")

    file_list: List[Path] = []
    for inp in parsed_args.inputs:
        p = Path(inp)
        if p.is_file():
            file_list.append(p)
        elif p.is_dir():
            for root, _, filenames in os.walk(p):
                for fname in sorted(filenames):
                    file_list.append(Path(root) / fname)

    if not file_list:
        logger.error("No input files found to join.")
        return 1

    dst = Path(parsed_args.output)
    ok = join_audio_files(file_list, dst)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
