"""Unit tests for base64_image_encoder module."""

import sys
from pathlib import Path

import pytest

# Ensure parent directory is on sys.path for direct import
SCRIPT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPT_DIR))

# pylint: disable=wrong-import-position
from base64_image_encoder import (  # noqa: E402
    decode_base64_to_image,
    encode_image_to_base64,
    main,
)


def test_encode_and_decode(tmp_path: Path) -> None:
    """Test round-trip encoding and decoding of an image file."""
    src_file = tmp_path / "sample.png"
    dst_file = tmp_path / "restored.png"
    sample_content = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR"
    src_file.write_bytes(sample_content)

    b64_uri = encode_image_to_base64(src_file, data_uri=True)
    assert b64_uri is not None
    assert b64_uri.startswith("data:image/png;base64,")

    ok = decode_base64_to_image(b64_uri, dst_file)
    assert ok is True
    assert dst_file.read_bytes() == sample_content


def test_cli_encode(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """Test CLI encode command."""
    img_file = tmp_path / "test.jpg"
    img_file.write_bytes(b"jpeg_data")

    ret = main(["encode", str(img_file), "--raw"])
    assert ret == 0
    captured = capsys.readouterr()
    assert len(captured.out.strip()) > 0


def test_cli_decode(tmp_path: Path) -> None:
    """Test CLI decode command."""
    txt_file = tmp_path / "b64.txt"
    out_img = tmp_path / "out.png"
    txt_file.write_text("data:image/png;base64,aGVsbG8=")

    ret = main(["decode", str(txt_file), "-o", str(out_img)])
    assert ret == 0
    assert out_img.read_bytes() == b"hello"
