"""Base plugin class for Universal Export Converter."""

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Dict, List


class BaseConverterPlugin(ABC):
    """Abstract base class for export converter plugins."""

    @abstractmethod
    def detect(self, file_path: Path) -> bool:
        """Detect whether the file is supported by this plugin.

        Args:
            file_path: Path to the file.

        Returns:
            True if supported, False otherwise.
        """

    @abstractmethod
    def convert(self, file_path: Path) -> List[Dict[str, Any]]:
        """Convert the export file into normalized records.

        Each normalized record must be a dict with keys:
            'timestamp': ISO 8601 string (e.g. YYYY-MM-DDTHH:MM:SSZ)
            'source': source service name (e.g. 'Slack', 'Google Takeout', etc.)
            'author': author or entity name
            'content': content of the entry (message, location details, etc.)

        Args:
            file_path: Path to the file to convert.

        Returns:
            List of normalized dictionary records.
        """
