"""Unit tests for NASA APOD Fetcher tool."""

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from main import fetch_apod_metadata, save_markdown_metadata, slugify


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


if __name__ == "__main__":
    unittest.main()
