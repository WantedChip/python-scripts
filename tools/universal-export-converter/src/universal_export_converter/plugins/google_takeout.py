# pylint: disable=duplicate-code
"""Google Takeout Location History converter plugin."""

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from universal_export_converter.base_plugin import BaseConverterPlugin


class GoogleTakeoutConverterPlugin(BaseConverterPlugin):
    """Parses and normalizes Google Takeout Location History JSON formats."""

    def detect(self, file_path: Path) -> bool:
        """Detect if the file is a Google Takeout Location History JSON file.

        Checks if the JSON root is a dictionary containing 'locations' or
        'timelineObjects'.
        """
        if not file_path.is_file() or file_path.suffix.lower() != ".json":
            return False

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                # Read a portion of file to check keys
                chunk = f.read(1024)
                if "locations" in chunk or "timelineObjects" in chunk:
                    return True
        except OSError:
            pass

        return False

    def _parse_timestamp(self, ts_ms: Any) -> str:
        """Helper to parse millisecond timestamp values."""
        if not ts_ms:
            return ""
        try:
            if isinstance(ts_ms, str) and not ts_ms.isdigit():
                return ts_ms
            dt = datetime.fromtimestamp(int(ts_ms) / 1000.0, tz=timezone.utc)
            return dt.isoformat()
        except (ValueError, TypeError):
            return str(ts_ms)

    def _convert_locations(self, locations: List[Any]) -> List[Dict[str, Any]]:
        """Helper to convert standard location list entries."""
        normalized: List[Dict[str, Any]] = []
        for loc in locations:
            if not isinstance(loc, dict):
                continue

            ts_ms = loc.get("timestampMs") or loc.get("timestamp")
            timestamp = self._parse_timestamp(ts_ms)

            lat = loc.get("latitudeE7")
            lng = loc.get("longitudeE7")
            lat_val = lat / 1e7 if isinstance(lat, (int, float)) else None
            lng_val = lng / 1e7 if isinstance(lng, (int, float)) else None

            accuracy = loc.get("accuracy", "unknown")
            content = f"Coordinates: ({lat_val}, {lng_val}) [Accuracy: {accuracy}]"

            normalized.append(
                {
                    "timestamp": timestamp,
                    "source": "Google Takeout Location History",
                    "author": "Location Sensor",
                    "content": content,
                }
            )
        return normalized

    def _convert_timeline(self, timeline: List[Any]) -> List[Dict[str, Any]]:
        """Helper to convert semantic timelineObjects entries."""
        # pylint: disable=too-many-locals
        normalized: List[Dict[str, Any]] = []
        for item in timeline:
            if not isinstance(item, dict):
                continue

            if "placeVisit" in item and isinstance(item["placeVisit"], dict):
                visit = item["placeVisit"]
                loc = visit.get("location", {})
                duration = visit.get("duration", {})
                start_ts = duration.get("startTimestampMs") or duration.get(
                    "startTimestamp"
                )
                timestamp = self._parse_timestamp(start_ts)

                lat = loc.get("latitudeE7")
                lng = loc.get("longitudeE7")
                lat_val = lat / 1e7 if isinstance(lat, (int, float)) else None
                lng_val = lng / 1e7 if isinstance(lng, (int, float)) else None
                name = loc.get("name") or loc.get("address") or "Unknown Place"

                normalized.append(
                    {
                        "timestamp": timestamp,
                        "source": "Google Takeout Semantic Location",
                        "author": "Semantic Log",
                        "content": f"Visited {name} ({lat_val}, {lng_val})",
                    }
                )

            elif "activitySegment" in item and isinstance(
                item["activitySegment"], dict
            ):
                act = item["activitySegment"]
                duration = act.get("duration", {})
                start_ts = duration.get("startTimestampMs") or duration.get(
                    "startTimestamp"
                )
                timestamp = self._parse_timestamp(start_ts)

                act_type = act.get("activityType", "MOVE")
                distance = act.get("distance", 0)

                normalized.append(
                    {
                        "timestamp": timestamp,
                        "source": "Google Takeout Activity Segment",
                        "author": "Activity Log",
                        "content": f"Activity: {act_type} (Distance: {distance}m)",
                    }
                )
        return normalized

    def convert(self, file_path: Path) -> List[Dict[str, Any]]:
        """Convert Location History into normalized records."""
        normalized: List[Dict[str, Any]] = []
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            if not isinstance(data, dict):
                return normalized

            # 1. Standard Locations format
            if "locations" in data and isinstance(data["locations"], list):
                normalized.extend(self._convert_locations(data["locations"]))

            # 2. Semantic Location History format (timelineObjects)
            elif "timelineObjects" in data and isinstance(
                data["timelineObjects"], list
            ):
                normalized.extend(self._convert_timeline(data["timelineObjects"]))

        except Exception:  # pylint: disable=broad-exception-caught  # nosec B110
            pass

        return normalized
