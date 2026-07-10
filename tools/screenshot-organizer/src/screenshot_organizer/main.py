"""CLI Screenshot Organizer.

Sorts and organizes screenshots by date, OCR text content, app/window clues,
and duplicate similarity.
"""

import argparse
import json
import logging
import re
import shutil
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# pylint: disable=import-error
import pytesseract
from PIL import ExifTags, Image

# Set up logging format
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".bmp", ".tiff", ".webp"}

DATE_PATTERNS = [
    # YYYY-MM-DD
    re.compile(
        r"(?:^|[^0-9])(20\d{2})[-_](0[1-9]|1[0-2])[-_](0[1-9]|[12]\d|3[01])(?:[^0-9]|$)"
    ),
    # YYYYMMDD
    re.compile(
        r"(?:^|[^0-9])(20\d{2})(0[1-9]|1[0-2])(0[1-9]|[12]\d|3[01])(?:[^0-9]|$)"
    ),
]

DEFAULT_APP_KEYWORDS = {
    "Chrome": ["chrome", "google chrome"],
    "VS Code": ["vs code", "vscode", "visual studio code"],
    "Slack": ["slack"],
    "Discord": ["discord"],
    "Spotify": ["spotify"],
    "Notepad": ["notepad"],
    "Excel": ["excel", "xlsx"],
    "Word": ["word", "docx"],
    "PowerPoint": ["powerpoint", "pptx"],
    "Zoom": ["zoom"],
    "Teams": ["teams", "microsoft teams"],
    "Terminal": ["terminal", "powershell", "cmd", "bash", "zsh"],
    "Figma": ["figma"],
    "Photoshop": ["photoshop", "psd"],
    "GitHub": ["github", "git"],
    "Jira": ["jira", "atlassian"],
}


# pylint: disable=too-many-instance-attributes
class ScreenshotOrganizer:
    """Organizer class containing settings and state for sorting screenshots."""

    # pylint: disable=too-many-arguments,too-many-positional-arguments
    def __init__(
        self,
        source_dir: Path,
        dest_dir: Path,
        action: str = "move",
        by_rules: Optional[List[str]] = None,
        date_format: str = "YYYY-MM-DD",
        ocr_enabled: bool = True,
        ocr_lang: str = "eng",
        app_keywords: Optional[Dict[str, List[str]]] = None,
        similarity_threshold: int = 4,
        dry_run: bool = False,
    ) -> None:
        """Initialize the organizer with configuration settings."""
        self.source_dir = source_dir
        self.dest_dir = dest_dir
        self.action = action
        self.by_rules = by_rules or ["date", "app", "duplicate"]
        self.date_format = date_format
        self.ocr_enabled = ocr_enabled
        self.ocr_lang = ocr_lang
        self.app_keywords = app_keywords or DEFAULT_APP_KEYWORDS
        self.similarity_threshold = similarity_threshold
        self.dry_run = dry_run

        # Initialize OCR capability flag
        self.ocr_available = False
        if self.ocr_enabled:
            self.ocr_available = self._check_ocr_availability()

    def _check_ocr_availability(self) -> bool:
        """Verify if pytesseract and Tesseract engine are available."""
        try:
            pytesseract.get_tesseract_version()
            return True
        # pylint: disable=broad-exception-caught
        except (pytesseract.TesseractNotFoundError, Exception) as err:
            logging.warning(
                "Tesseract OCR is not installed or not in PATH: %s. "
                "OCR features will be bypassed.",
                err,
            )
            return False

    def get_image_files(self) -> List[Path]:
        """Scan the source directory for supported image files."""
        if not self.source_dir.exists():
            logging.error("Source directory %s does not exist.", self.source_dir)
            return []

        image_files = []
        for file_path in self.source_dir.iterdir():
            if file_path.is_file() and file_path.suffix.lower() in IMAGE_EXTENSIONS:
                image_files.append(file_path)

        # Sort files by creation/modification date (oldest first)
        # to guarantee the oldest copy in a duplicate cluster is treated as primary.
        image_files.sort(key=self.extract_date_from_mtime)
        return image_files

    @staticmethod
    def extract_date_from_mtime(image_path: Path) -> datetime:
        """Get datetime from file modification and creation times.

        Uses the older of the two.
        """
        stat = image_path.stat()
        mtime = stat.st_mtime
        try:
            ctime = stat.st_ctime
            best_time = min(mtime, ctime)
        except Exception:  # pylint: disable=broad-exception-caught
            best_time = mtime
        return datetime.fromtimestamp(best_time)

    def extract_date(self, image_path: Path) -> datetime:
        """Extract a sorting date from filename, EXIF metadata, or filesystem mtime."""
        # 1. Try filename regex
        for pattern in DATE_PATTERNS:
            match = pattern.search(image_path.name)
            if match:
                try:
                    year, month, day = map(int, match.groups())
                    return datetime(year, month, day)
                except ValueError:
                    continue

        # 2. Try EXIF data
        try:
            with Image.open(image_path) as img:
                exif_data = img.getexif()
                if exif_data:
                    for tag_id, value in exif_data.items():
                        tag = ExifTags.TAGS.get(tag_id, tag_id)
                        if tag in (
                            "DateTimeOriginal",
                            "DateTimeDigitized",
                            "DateTime",
                        ) and isinstance(value, str):
                            match = re.match(r"^(\d{4}):(\d{2}):(\d{2})", value)
                            if match:
                                year, month, day = map(int, match.groups())
                                return datetime(year, month, day)
        except Exception as err:  # pylint: disable=broad-exception-caught
            logging.debug("Failed to read EXIF from %s: %s", image_path, err)

        # 3. Fall back to filesystem mtime/ctime
        return self.extract_date_from_mtime(image_path)

    @staticmethod
    def extract_app_from_filename(filename: str) -> Optional[str]:
        """Extract application clues from filename markers like ' - App' or '(App)'."""
        stem = Path(filename).stem
        # Try trailing text in parentheses, e.g. "Screenshot 123 (Google Chrome)"
        match = re.search(r"\(([^)]+)\)$", stem)
        if match:
            return match.group(1).strip()
        # Try trailing text after a dash, e.g. "Screenshot 123 - VS Code"
        match = re.search(r"\s+-\s+([^-]+)$", stem)
        if match:
            return match.group(1).strip()
        return None

    def extract_app_from_ocr(self, image_path: Path) -> Optional[str]:
        """Perform OCR on the image and scan for application keywords."""
        if not self.ocr_available:
            return None

        try:
            with Image.open(image_path) as img:
                text = pytesseract.image_to_string(img, lang=self.ocr_lang).lower()

            # Sort keywords by length in descending order
            # to match most specific keywords first
            match_candidates: List[Tuple[str, str, int]] = []
            for app_name, keywords in self.app_keywords.items():
                for keyword in keywords:
                    keyword_lower = keyword.lower()
                    if keyword_lower in text:
                        match_candidates.append(
                            (app_name, keyword_lower, len(keyword_lower))
                        )

            if match_candidates:
                # Return the app name associated with the longest matching keyword
                match_candidates.sort(key=lambda item: item[2], reverse=True)
                return match_candidates[0][0]
        except Exception as err:  # pylint: disable=broad-exception-caught
            logging.error("OCR extraction failed for %s: %s", image_path, err)

        return None

    def get_app_clue(self, image_path: Path) -> Optional[str]:
        """Retrieve app/window clue from filename or OCR content."""
        # Check filename first
        app = self.extract_app_from_filename(image_path.name)
        if app:
            return app

        # Check OCR second (if enabled)
        if "app" in self.by_rules:
            return self.extract_app_from_ocr(image_path)

        return None

    @staticmethod
    def compute_dhash(image_path: Path) -> Optional[str]:
        """Compute 64-bit Difference Hash (dHash) for an image."""
        try:
            with Image.open(image_path) as img:
                # Convert to grayscale and resize to 9x8
                img_gray = img.convert("L").resize((9, 8), Image.Resampling.BILINEAR)
                pixels = list(img_gray.getdata())

                difference = []
                for row in range(8):
                    for col in range(8):
                        pixel_left = pixels[row * 9 + col]
                        pixel_right = pixels[row * 9 + col + 1]
                        difference.append(pixel_left > pixel_right)

                decimal_value = 0
                for index, value in enumerate(difference):
                    if value:
                        decimal_value += 2**index

                return f"{decimal_value:016x}"
        except Exception as err:  # pylint: disable=broad-exception-caught
            logging.error("Failed to compute dHash for %s: %s", image_path, err)
            return None

    @staticmethod
    def hamming_distance(hash1: str, hash2: str) -> int:
        """Calculate Hamming distance between two hex hashes."""
        try:
            val1 = int(hash1, 16)
            val2 = int(hash2, 16)
            return bin(val1 ^ val2).count("1")
        except ValueError:
            return 999

    def group_by_similarity(
        self, image_files: List[Path]
    ) -> Tuple[List[Path], Dict[Path, List[Path]]]:
        """Cluster image files by perceptual similarity using dHash Hamming distance.

        Returns:
            A tuple of (primary_files, duplicate_mapping)
        """
        # Dictionary of primary file path to computed dHash
        primaries: Dict[Path, str] = {}
        # Mapping of primary file to its duplicates
        duplicates_map: Dict[Path, List[Path]] = {}

        for file_path in image_files:
            file_hash = self.compute_dhash(file_path)
            if not file_hash:
                # If hashing fails, treat as a unique primary
                primaries[file_path] = ""
                continue

            matched_primary = None
            for prim_path, prim_hash in primaries.items():
                dist = self.hamming_distance(file_hash, prim_hash)
                if prim_hash and dist <= self.similarity_threshold:
                    matched_primary = prim_path
                    break

            if matched_primary:
                logging.info(
                    "Detected duplicate: %s (similar to %s)",
                    file_path.name,
                    matched_primary.name,
                )
                if matched_primary not in duplicates_map:
                    duplicates_map[matched_primary] = []
                duplicates_map[matched_primary].append(file_path)
            else:
                primaries[file_path] = file_hash

        return list(primaries.keys()), duplicates_map

    def format_date_folder(self, date_val: datetime) -> str:
        """Format the date folder name based on date_format choice."""
        if self.date_format == "YYYY/MM":
            return date_val.strftime("%Y/%m")
        if self.date_format == "YYYY-MM":
            return date_val.strftime("%Y-%m")
        # Default: YYYY-MM-DD
        return date_val.strftime("%Y-%m-%d")

    def determine_dest_folder(self, image_path: Path) -> Path:
        """Calculate destination folder path according to the 'by_rules' hierarchy."""
        subpath = Path()

        for rule in self.by_rules:
            if rule == "date":
                date_val = self.extract_date(image_path)
                subpath = subpath / self.format_date_folder(date_val)
            elif rule == "app":
                app_clue = self.get_app_clue(image_path)
                if app_clue:
                    # Clean up application name for path safety
                    clean_app = re.sub(r'[\\/*?:"<>|]', "", app_clue)
                    subpath = subpath / clean_app
                else:
                    # Default: put in no-app folder or keep same level
                    subpath = subpath / "misc"

        return self.dest_dir / subpath

    @staticmethod
    def get_unique_target(target_path: Path) -> Path:
        """Check if path exists, and append increments to keep names unique."""
        if not target_path.exists():
            return target_path

        stem = target_path.stem
        suffix = target_path.suffix
        parent = target_path.parent
        counter = 1
        while True:
            new_path = parent / f"{stem}_{counter}{suffix}"
            if not new_path.exists():
                return new_path
            counter += 1

    def execute_file_action(self, source: Path, target: Path) -> None:
        """Perform move/copy operation depending on settings."""
        action_desc = "Would move" if self.dry_run else "Moving"
        if self.action == "copy":
            action_desc = "Would copy" if self.dry_run else "Copying"

        logging.info("%s %s -> %s", action_desc, source.name, target)

        if not self.dry_run:
            target.parent.mkdir(parents=True, exist_ok=True)
            if self.action == "copy":
                shutil.copy2(source, target)
            else:
                shutil.move(str(source), str(target))

    def organize(self) -> None:
        """Scan source directory, group duplicates, and sort primary files."""
        image_files = self.get_image_files()
        if not image_files:
            logging.info("No screenshots found to organize.")
            return

        # 1. Perform similarity check if requested
        if "duplicate" in self.by_rules:
            primaries, duplicates_map = self.group_by_similarity(image_files)
        else:
            primaries = image_files
            duplicates_map = {}

        # 2. Process primary files
        for primary in primaries:
            dest_folder = self.determine_dest_folder(primary)
            target_path = self.get_unique_target(dest_folder / primary.name)
            self.execute_file_action(primary, target_path)

            # 3. Process duplicates for this primary
            if primary in duplicates_map:
                duplicate_folder = self.dest_dir / "duplicates" / primary.stem
                metadata_records = []

                for dup in duplicates_map[primary]:
                    dup_target = self.get_unique_target(duplicate_folder / dup.name)
                    self.execute_file_action(dup, dup_target)
                    metadata_records.append(
                        {
                            "original_name": dup.name,
                            "final_path": str(dup_target),
                            "mtime": self.extract_date_from_mtime(dup).isoformat(),
                        }
                    )

                # Write duplicate info log inside the group folder
                if not self.dry_run:
                    duplicate_folder.mkdir(parents=True, exist_ok=True)
                    meta_path = duplicate_folder / "metadata.json"
                    meta_content = {
                        "primary_file": {
                            "original_name": primary.name,
                            "organized_to": str(target_path),
                        },
                        "duplicates": metadata_records,
                    }
                    try:
                        with open(meta_path, "w", encoding="utf-8") as f_meta:
                            json.dump(meta_content, f_meta, indent=2)
                    except Exception as err:  # pylint: disable=broad-exception-caught
                        logging.error(
                            "Failed to write metadata for duplicates of %s: %s",
                            primary.name,
                            err,
                        )

        logging.info("Screenshots organization complete.")


def parse_app_keywords(arg: Optional[str]) -> Optional[Dict[str, List[str]]]:
    """Parse application keywords configuration from CLI argument."""
    if not arg:
        return None

    # Check if arg points to a JSON file
    path = Path(arg)
    if path.is_file():
        try:
            with open(path, "r", encoding="utf-8") as f_keywords:
                data = json.load(f_keywords)
                if isinstance(data, dict):
                    # Ensure values are lists of strings
                    return {
                        str(k): (
                            [str(v) for v in val]
                            if isinstance(val, list)
                            else [str(val)]
                        )
                        for k, val in data.items()
                    }
        except Exception as err:  # pylint: disable=broad-exception-caught
            raise argparse.ArgumentTypeError(
                f"Failed to parse keywords JSON file: {err}"
            ) from err

    # Otherwise, try parsing comma-separated key=val1|val2 values
    try:
        keywords = {}
        for item in arg.split(","):
            if "=" in item:
                key, val_str = item.split("=", 1)
                keywords[key.strip()] = [
                    v.strip() for v in val_str.split("|") if v.strip()
                ]
        if keywords:
            return keywords
    except Exception as err:  # pylint: disable=broad-exception-caught
        raise argparse.ArgumentTypeError(
            "Invalid keywords string format. Expected "
            f"'App=word1|word2,App2=word3': {err}"
        ) from err

    raise argparse.ArgumentTypeError(
        "Keywords must be a valid JSON file path or a "
        "comma-separated key=val1|val2 format."
    )


def main() -> None:
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="CLI Screenshot Organizer — sort screenshots by date, OCR text, "
        "app/window clues, and duplicate similarity."
    )
    parser.add_argument(
        "source_dir",
        type=Path,
        help="Source directory containing screenshots.",
    )
    parser.add_argument(
        "dest_dir",
        type=Path,
        help="Destination directory to organize screenshots into.",
    )
    parser.add_argument(
        "--action",
        choices=["move", "copy"],
        default="move",
        help="File operation to perform (default: move).",
    )
    parser.add_argument(
        "--by",
        default="date,app,duplicate",
        help="Comma-separated hierarchy of sorting criteria: "
        "date, app, duplicate (default: date,app,duplicate).",
    )
    parser.add_argument(
        "--date-format",
        choices=["YYYY-MM-DD", "YYYY-MM", "YYYY/MM"],
        default="YYYY-MM-DD",
        help="Date folder structure style (default: YYYY-MM-DD).",
    )
    parser.add_argument(
        "--no-ocr",
        dest="ocr",
        action="store_false",
        help="Disable OCR extraction of application clues.",
    )
    parser.add_argument(
        "--ocr-lang",
        default="eng",
        help="Tesseract OCR language code (default: eng).",
    )
    parser.add_argument(
        "--app-keywords",
        type=parse_app_keywords,
        help="JSON file path or key-val string (e.g. 'Chrome=chrome,"
        "Discord=discord') for app categorization.",
    )
    parser.add_argument(
        "--similarity-threshold",
        type=int,
        default=4,
        help="Hamming distance threshold for duplicate grouping (0-64, default: 4).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview operations without performing any filesystem changes.",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Enable verbose output logging.",
    )

    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    by_rules = [r.strip() for r in args.by.split(",") if r.strip()]

    organizer = ScreenshotOrganizer(
        source_dir=args.source_dir,
        dest_dir=args.dest_dir,
        action=args.action,
        by_rules=by_rules,
        date_format=args.date_format,
        ocr_enabled=args.ocr,
        ocr_lang=args.ocr_lang,
        app_keywords=args.app_keywords,
        similarity_threshold=args.similarity_threshold,
        dry_run=args.dry_run,
    )

    organizer.organize()


if __name__ == "__main__":
    main()
