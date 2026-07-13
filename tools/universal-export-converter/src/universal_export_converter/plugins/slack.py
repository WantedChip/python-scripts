# pylint: disable=duplicate-code
"""Slack export converter plugin."""

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from universal_export_converter.base_plugin import BaseConverterPlugin


class SlackConverterPlugin(BaseConverterPlugin):
    """Parses and normalizes Slack export JSON files."""

    def detect(self, file_path: Path) -> bool:
        """Detect if the file is a Slack export JSON file.

        Checks if the file is a JSON array where elements have keys typical
        for Slack messages, like 'ts' and 'text'.
        """
        if not file_path.is_file() or file_path.suffix.lower() != ".json":
            return False

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                # Read a snippet to avoid parsing huge files if they aren't JSON
                data = json.load(f)
                if not isinstance(data, list):
                    return False
                if not data:
                    return True  # Empty list can be parsed, but let's assume it matches

                # Check if first element contains typical Slack keys
                first = data[0]
                if isinstance(first, dict) and "ts" in first and "text" in first:
                    return True
        except (json.JSONDecodeError, OSError):
            pass

        return False

    def convert(self, file_path: Path) -> List[Dict[str, Any]]:
        """Convert Slack messages list into normalized format."""
        normalized: List[Dict[str, Any]] = []
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            if not isinstance(data, list):
                return normalized

            for msg in data:
                if not isinstance(msg, dict):
                    continue

                # Parse timestamp
                ts_raw = msg.get("ts")
                timestamp = ""
                if ts_raw:
                    try:
                        # Slack timestamps are usually epoch strings
                        # e.g. "1512086400.000002"
                        ts_float = float(ts_raw)
                        dt = datetime.fromtimestamp(ts_float, tz=timezone.utc)
                        timestamp = dt.isoformat()
                    except (ValueError, TypeError):
                        timestamp = str(ts_raw)

                # Author
                author = msg.get("user") or msg.get("username") or "System"

                # Content
                content = msg.get("text", "")

                # Skip threads/replies metadata or subtype events if appropriate,
                # but let's normalize everything as content.
                normalized.append(
                    {
                        "timestamp": timestamp,
                        "source": "Slack",
                        "author": str(author),
                        "content": str(content),
                    }
                )
        except Exception:  # pylint: disable=broad-exception-caught  # nosec B110
            pass

        return normalized
