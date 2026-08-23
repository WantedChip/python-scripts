"""Unit tests for NASA APOD Fetcher tool."""

import io
import json
import tempfile
import unittest
import urllib.error
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

from main import (
    download_image,
    fetch_apod_metadata,
    main,
    save_markdown_metadata,
    slugify,
)


def _http_error(code: int, reason: str, body: bytes) -> urllib.error.HTTPError:
    """Build a real HTTPError with a readable body."""
    return urllib.error.HTTPError(
        "https://api.nasa.gov/planetary/apod",
        code,
        reason,
        None,
        io.BytesIO(body),
    )


class TestNasaApodFetcher(unittest.TestCase):
    """Test suite for NASA APOD Fetcher functions."""

    def test_slugify(self) -> None:
        self.assertEqual(slugify("Hello World! 2026"), "hello_world_2026")
        self.assertEqual(
            slugify("Cosmic Nebulae: Cygnus Loop"), "cosmic_nebulae_cygnus_loop"
        )

    @patch("urllib.request.urlopen")
    def test_fetch_apod_metadata_success(self, mock_urlopen: MagicMock) -> None:
        mock_response = MagicMock()
        mock_response.status = 200
        mock_data = {
            "date": "2026-07-24",
            "title": "Andromeda Galaxy",
            "explanation": "A vast spiral galaxy...",
            "url": "https://apod.nasa.gov/apod/image/2607/andromeda.jpg",
            "media_type": "image",
        }
        mock_response.read.return_value = json.dumps(mock_data).encode("utf-8")
        mock_urlopen.return_value.__enter__.return_value = mock_response

        meta = fetch_apod_metadata("DEMO_KEY", "2026-07-24")
        self.assertEqual(meta["title"], "Andromeda Galaxy")
        self.assertEqual(meta["media_type"], "image")

    def test_save_markdown_metadata(self) -> None:
        metadata = {
            "title": "Orion Nebula",
            "date": "2026-07-24",
            "copyright": "NASA",
            "explanation": "Star-forming region...",
            "url": "https://example.com/orion.jpg",
        }

        with tempfile.NamedTemporaryFile("w+", delete=False, suffix=".md") as tmp:
            tmp_path = Path(tmp.name)

        try:
            save_markdown_metadata(metadata, tmp_path, image_filename="orion.jpg")
            content = tmp_path.read_text(encoding="utf-8")
            self.assertIn("# Orion Nebula", content)
            self.assertIn("![Orion Nebula](orion.jpg)", content)
            self.assertIn("Star-forming region...", content)
        finally:
            if tmp_path.exists():
                tmp_path.unlink()

    def test_save_markdown_metadata_defaults_and_hdurl(self) -> None:
        """Missing copyright falls back to NASA; hdurl wins over url."""
        metadata = {
            "title": "Test Picture",
            "explanation": "  An explanation.  ",
            "hdurl": "https://example.com/hd.png",
            "url": "https://example.com/sd.jpg",
            "media_type": "image",
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            md_path = Path(tmpdir) / "out.md"
            save_markdown_metadata(metadata, md_path)
            content = md_path.read_text(encoding="utf-8")
        self.assertIn("**Copyright**: Public Domain / NASA", content)
        self.assertIn("[https://example.com/hd.png]", content)
        self.assertNotIn("sd.jpg", content)
        self.assertIn("An explanation.", content)


class TestMetadataErrorPaths(unittest.TestCase):
    """Tests for API error handling in fetch_apod_metadata."""

    @patch("urllib.request.urlopen")
    def test_non_200_status_raises_runtime_error(self, mock_urlopen: MagicMock) -> None:
        """Unexpected success-path statuses raise RuntimeError."""
        mock_resp = MagicMock()
        mock_resp.status = 503
        mock_urlopen.return_value.__enter__.return_value = mock_resp

        with self.assertRaisesRegex(RuntimeError, "HTTP Status 503"):
            fetch_apod_metadata("KEY")

    @patch("urllib.request.urlopen")
    def test_rate_limit_error_mentions_custom_key(
        self, mock_urlopen: MagicMock
    ) -> None:
        """HTTP 429 surfaces a rate-limit hint about custom keys."""
        mock_urlopen.side_effect = _http_error(429, "Too Many Requests", b"")
        with self.assertRaisesRegex(RuntimeError, "Rate limit exceeded"):
            fetch_apod_metadata("DEMO_KEY")

    @patch("urllib.request.urlopen")
    def test_client_error_surfaces_response_body(self, mock_urlopen: MagicMock) -> None:
        """HTTP 400/403/404 errors include the API response body."""
        mock_urlopen.side_effect = _http_error(
            400, "Bad Request", b'{"error": "Date must be between..."}'
        )
        with self.assertRaisesRegex(ValueError, "Date must be between"):
            fetch_apod_metadata("DEMO_KEY", date="1800-01-01")

    @patch("urllib.request.urlopen")
    def test_server_error_raises_runtime_error(self, mock_urlopen: MagicMock) -> None:
        """Other HTTP codes raise a plain RuntimeError."""
        mock_urlopen.side_effect = _http_error(500, "Internal Server Error", b"x")
        with self.assertRaisesRegex(RuntimeError, "HTTP Error 500"):
            fetch_apod_metadata("DEMO_KEY")

    @patch("urllib.request.urlopen")
    def test_url_error_raises_runtime_error(self, mock_urlopen: MagicMock) -> None:
        """Network failures raise RuntimeError mentioning NASA API."""
        mock_urlopen.side_effect = urllib.error.URLError("no route to host")
        with self.assertRaisesRegex(RuntimeError, "Network error"):
            fetch_apod_metadata("DEMO_KEY")


class TestDownloadImage(unittest.TestCase):
    """Tests for binary image download."""

    @patch("main.urllib.request.urlopen")
    def test_download_image_writes_bytes(self, mock_urlopen: MagicMock) -> None:
        """The response body is written verbatim to the destination."""
        png_bytes = b"\x89PNG\r\n\x1a\nfake-image-data"
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.read.return_value = png_bytes
        mock_urlopen.return_value.__enter__.return_value = mock_resp

        with tempfile.TemporaryDirectory() as tmpdir:
            dest = Path(tmpdir) / "picture.jpg"
            download_image("https://apod.nasa.gov/img.jpg", dest)
            self.assertEqual(dest.read_bytes(), png_bytes)
        request = mock_urlopen.call_args[0][0]
        self.assertIn("apod.nasa.gov/img.jpg", request.full_url)

    @patch("main.urllib.request.urlopen")
    def test_download_image_http_error_propagates(
        self, mock_urlopen: MagicMock
    ) -> None:
        """Download failures propagate to the CLI error handler."""
        mock_urlopen.side_effect = _http_error(404, "Not Found", b"gone")
        with tempfile.TemporaryDirectory() as tmpdir:
            dest = Path(tmpdir) / "missing.jpg"
            with self.assertRaises(urllib.error.HTTPError):
                download_image("https://apod.nasa.gov/none.jpg", dest)


class TestCli(unittest.TestCase):
    """CLI-level tests covering main() flows via sys.argv."""

    METADATA = {
        "date": "2026-07-24",
        "title": "Andromeda Galaxy!",
        "explanation": "A vast spiral galaxy.",
        "copyright": "NASA",
        "url": "https://apod.nasa.gov/image.jpg",
        "hdurl": "https://apod.nasa.gov/image_full.jpg",
        "media_type": "image",
    }

    def _run_cli(self, *args: str) -> Any:
        """Run main() with patched argv; capture streams and exit code."""
        stdout, stderr = io.StringIO(), io.StringIO()
        exit_code: Any = None
        argv = ["main.py"] + list(args)
        with redirect_stdout(stdout), redirect_stderr(stderr), patch("sys.argv", argv):
            try:
                main()
            except SystemExit as exc:
                exit_code = exc.code
        return stdout.getvalue(), stderr.getvalue(), exit_code

    @patch("main.download_image")
    @patch("main.fetch_apod_metadata")
    def test_cli_downloads_image_and_saves_markdown(
        self, mock_fetch: MagicMock, mock_download: MagicMock
    ) -> None:
        """Image media types download a file next to the Markdown report."""
        mock_fetch.return_value = dict(self.METADATA)
        with tempfile.TemporaryDirectory() as tmpdir:
            out_dir = Path(tmpdir) / "photos"
            stdout, _, code = self._run_cli("-k", "MYKEY", "-o", str(out_dir))
            self.assertIsNone(code)
            self.assertIn("Downloading APOD image from", stdout)
            self.assertIn("Saved image to", stdout)
            md_files = list(out_dir.glob("*.md"))
            self.assertEqual(len(md_files), 1)
            content = md_files[0].read_text(encoding="utf-8")
        self.assertEqual(md_files[0].name, "2026-07-24_andromeda_galaxy.md")
        self.assertIn("![Andromeda Galaxy!](2026-07-24_andromeda_galaxy.jpg)", content)
        self.assertIn("Title: Andromeda Galaxy!", stdout)
        mock_download.assert_called_once()
        img_arg = mock_download.call_args[0][1]
        self.assertEqual(img_arg.suffix, ".jpg")

    @patch("main.download_image")
    @patch("main.fetch_apod_metadata")
    def test_cli_video_media_type_skips_download(
        self, mock_fetch: MagicMock, mock_download: MagicMock
    ) -> None:
        """Non-image media types skip the download step entirely."""
        payload = dict(self.METADATA)
        payload["media_type"] = "video"
        payload["url"] = "https://youtube.com/watch?v=xyz"
        mock_fetch.return_value = payload
        with tempfile.TemporaryDirectory() as tmpdir:
            out_dir = Path(tmpdir) / "out"
            stdout, _, code = self._run_cli("-o", str(out_dir))
            self.assertIsNone(code)
            content = (out_dir / "2026-07-24_andromeda_galaxy.md").read_text(
                encoding="utf-8"
            )
        self.assertIn("Media Type**: video", content)
        self.assertNotIn("![]", content)
        mock_download.assert_not_called()

    @patch("main.download_image")
    @patch("main.fetch_apod_metadata")
    def test_cli_no_download_flag(
        self, mock_fetch: MagicMock, mock_download: MagicMock
    ) -> None:
        """--no-download fetches metadata without touching the image URL."""
        mock_fetch.return_value = dict(self.METADATA)
        with tempfile.TemporaryDirectory() as tmpdir:
            out_dir = Path(tmpdir) / "out"
            stdout, _, code = self._run_cli("-o", str(out_dir), "--no-download")
            self.assertIsNone(code)
            self.assertNotIn("Downloading APOD image", stdout)
        mock_download.assert_not_called()
        self.assertIn("Saved metadata to", stdout)

    @patch("main.fetch_apod_metadata")
    def test_cli_fetch_failure_exits_one(self, mock_fetch: MagicMock) -> None:
        """Metadata failures print the error to stderr and exit 1."""
        mock_fetch.side_effect = RuntimeError("Rate limit exceeded for DEMO_KEY.")
        _, stderr, code = self._run_cli()
        self.assertEqual(code, 1)
        self.assertIn("Error: Rate limit exceeded", stderr)


if __name__ == "__main__":
    unittest.main()
