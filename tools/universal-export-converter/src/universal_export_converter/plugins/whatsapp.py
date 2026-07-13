# pylint: disable=duplicate-code
"""WhatsApp chat export converter plugin."""

import re
from pathlib import Path
from typing import Any, Dict, List

from universal_export_converter.base_plugin import BaseConverterPlugin

# Regex patterns to match WhatsApp message headers
PATTERNS = [
    # Format with square brackets: [15/01/2021, 10:24:00] Author: message
    re.compile(
        r"^\[(\d{1,4}[/\-.]\d{1,2}[/\-.]\d{1,4}),?\s+"
        r"(\d{1,2}:\d{2}(?::\d{2})?(?:\s*[aApP][mM])?)\]\s+"
        r"([^:]+):\s*(.*)$"
    ),
    # Format with dash: 15/01/2021, 10:24 - Author: message
    re.compile(
        r"^(\d{1,4}[/\-.]\d{1,2}[/\-.]\d{1,4}),?\s+"
        r"(\d{1,2}:\d{2}(?::\d{2})?(?:\s*[aApP][mM])?)\s+-\s+"
        r"([^:]+):\s*(.*)$"
    ),
    # Format with colon: 15/01/2021, 10:24: Author: message
    re.compile(
        r"^(\d{1,4}[/\-.]\d{1,2}[/\-.]\d{1,4}),?\s+"
        r"(\d{1,2}:\d{2}(?::\d{2})?(?:\s*[aApP][mM])?):\s+"
        r"([^:]+):\s*(.*)$"
    ),
]


class WhatsappConverterPlugin(BaseConverterPlugin):
    """Parses and normalizes WhatsApp chat export .txt files."""

    def detect(self, file_path: Path) -> bool:
        """Detect if the file is a WhatsApp chat export.

        Reads first few lines and checks if any match the expected formats.
        """
        if not file_path.is_file() or file_path.suffix.lower() != ".txt":
            return False

        try:
            with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                for _ in range(20):
                    line = f.readline()
                    if not line:
                        break
                    line = line.strip()
                    for pattern in PATTERNS:
                        if pattern.match(line):
                            return True
        except OSError:
            pass

        return False

    def convert(self, file_path: Path) -> List[Dict[str, Any]]:
        """Convert WhatsApp chat export into normalized records."""
        normalized: List[Dict[str, Any]] = []
        current_msg: Dict[str, Any] = {}

        try:
            with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                for line in f:
                    line_str = line.rstrip("\r\n")

                    # Check if line matches a new message header
                    matched = False
                    for pattern in PATTERNS:
                        match = pattern.match(line_str)
                        if match:
                            # Save previous message first
                            if current_msg:
                                normalized.append(current_msg)

                            date_part = match.group(1)
                            time_part = match.group(2)
                            timestamp = f"{date_part} {time_part}"
                            author = match.group(3).strip()
                            content = match.group(4)

                            current_msg = {
                                "timestamp": timestamp,
                                "source": "WhatsApp",
                                "author": author,
                                "content": content,
                            }
                            matched = True
                            break

                    if not matched:
                        # This line is a continuation of the previous message's content
                        if current_msg:
                            current_msg["content"] += "\n" + line_str
                        else:
                            # File contains non-matching header lines, skip
                            continue

                # Don't forget the last message
                if current_msg:
                    normalized.append(current_msg)

        except Exception:  # pylint: disable=broad-exception-caught  # nosec B110
            pass

        return normalized
