"""NASA Astronomy Picture of the Day (APOD) Fetcher.

Downloads NASA APOD image and saves description metadata as a Markdown report file.
"""

import argparse
import datetime
import json
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, Optional, cast


def fetch_apod_metadata(
    api_key: str = "DEMO_KEY", date: Optional[str] = None
) -> Dict[str, Any]:
    """Fetch APOD metadata from NASA API.

    Args:
        api_key: NASA API key (defaults to 'DEMO_KEY').
        date: Optional date string in YYYY-MM-DD format.

    Returns:
        Dictionary containing APOD metadata.

    Raises:
        ValueError: If API key is invalid or date format is wrong.
        RuntimeError: On HTTP/network errors.
    """
    params = f"api_key={api_key.strip()}"
    if date:
        params += f"&date={date.strip()}"

    url = f"https://api.nasa.gov/planetary/apod?{params}"

    req = urllib.request.Request(
        url,
        headers={"User-Agent": "NASA-APOD-Fetcher/1.0 (Python)"},
    )

    try:
        with urllib.request.urlopen(req, timeout=12) as response:  # nosec B310
            if response.status == 200:
                return cast(Dict[str, Any], json.loads(response.read().decode("utf-8")))
            raise RuntimeError(f"HTTP Status {response.status}")
    except urllib.error.HTTPError as err:
        if err.code == 429:
            raise RuntimeError(
                "NASA API Rate limit exceeded for DEMO_KEY. "
                "Please provide a custom NASA API key."
            ) from err
        if err.code in (400, 403, 404):
            err_msg = err.read().decode("utf-8") if hasattr(err, "read") else str(err)
            raise ValueError(f"NASA API Request error: {err_msg}") from err
        raise RuntimeError(f"HTTP Error {err.code}: {err.reason}") from err
    except urllib.error.URLError as err:
        raise RuntimeError(
            f"Network error connecting to NASA API: {err.reason}"
        ) from err


def slugify(text: str) -> str:
    """Convert title string into a safe file slug.

    Args:
        text: String to sanitize.

    Returns:
        Slugified string.
    """
    clean = re.sub(r"[^\w\s-]", "", text).strip().lower()
    return re.sub(r"[-\s]+", "_", clean)


def download_image(url: str, dest_path: Path) -> None:
    """Download image file from URL to destination path.

    Args:
        url: Image web URL.
        dest_path: Output file path.
    """
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "NASA-APOD-Fetcher/1.0 (Python)"},
    )
    with urllib.request.urlopen(req, timeout=30) as response:  # nosec B310
        dest_path.write_bytes(response.read())


def save_markdown_metadata(
    metadata: Dict[str, Any], dest_path: Path, image_filename: Optional[str] = None
) -> None:
    """Save APOD description metadata into a clean Markdown document.

    Args:
        metadata: APOD metadata dict.
        dest_path: File path for destination .md file.
        image_filename: Relative image filename if downloaded.
    """
    title = metadata.get("title", "NASA Astronomy Picture of the Day")
    date_str = metadata.get("date", "N/A")
    copyright_str = metadata.get("copyright", "Public Domain / NASA")
    explanation = metadata.get("explanation", "").strip()
    media_url = metadata.get("hdurl") or metadata.get("url", "")
    media_type = metadata.get("media_type", "image")

    lines = [
        f"# {title}",
        "",
        f"- **Date**: {date_str}",
        f"- **Copyright**: {copyright_str}",
        f"- **Media Type**: {media_type}",
        f"- **Original Source URL**: [{media_url}]({media_url})",
        "",
    ]

    if image_filename:
        lines.extend([f"![{title}]({image_filename})", ""])

    lines.extend(
        [
            "## Description",
            "",
            explanation,
            "",
        ]
    )

    dest_path.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    """CLI entry point for NASA APOD Fetcher."""
    parser = argparse.ArgumentParser(
        description="Download NASA Astronomy Picture of the Day (APOD) and metadata."
    )
    parser.add_argument(
        "-k",
        "--api-key",
        default="DEMO_KEY",
        help="NASA API Key (default: DEMO_KEY).",
    )
    parser.add_argument(
        "-d",
        "--date",
        help="Date for APOD in YYYY-MM-DD format (default: today).",
    )
    parser.add_argument(
        "-o",
        "--output-dir",
        type=Path,
        default=Path("./apod_output"),
        help="Directory to save downloaded files (default: ./apod_output).",
    )
    parser.add_argument(
        "--no-download",
        action="store_true",
        help="Fetch metadata only without downloading image file.",
    )

    args = parser.parse_args()

    try:
        metadata = fetch_apod_metadata(api_key=args.api_key, date=args.date)

        date_val = metadata.get("date", datetime.date.today().isoformat())
        title_slug = slugify(metadata.get("title", "apod"))
        base_name = f"{date_val}_{title_slug}"

        args.output_dir.mkdir(parents=True, exist_ok=True)
        md_file = args.output_dir / f"{base_name}.md"

        image_filename: Optional[str] = None
        media_type = metadata.get("media_type", "image")
        media_url = metadata.get("url", "")

        if not args.no_download and media_type == "image" and media_url:
            ext = Path(media_url).suffix or ".jpg"
            if "?" in ext:
                ext = ext.split("?")[0]
            img_file = args.output_dir / f"{base_name}{ext}"
            print(f"Downloading APOD image from {media_url}...")
            download_image(media_url, img_file)
            image_filename = img_file.name
            print(f"Saved image to {img_file}")

        save_markdown_metadata(metadata, md_file, image_filename=image_filename)
        print(f"Saved metadata to {md_file}")

        print("\n=== NASA APOD Summary ===")
        print(f"Title: {metadata.get('title')}")
        print(f"Date:  {metadata.get('date')}")
        print(f"URL:   {media_url}")

    except Exception as err:  # pylint: disable=broad-exception-caught
        print(f"Error: {err}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
