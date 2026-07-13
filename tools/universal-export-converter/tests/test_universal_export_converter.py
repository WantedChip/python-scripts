"""Unit tests for Universal Export Converter."""

import csv
import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

# Insert src directory to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from universal_export_converter.main import auto_detect_plugin, main  # noqa: E402
from universal_export_converter.plugins.google_takeout import (  # noqa: E402
    GoogleTakeoutConverterPlugin,
)
from universal_export_converter.plugins.slack import SlackConverterPlugin  # noqa: E402
from universal_export_converter.plugins.whatsapp import (  # noqa: E402
    WhatsappConverterPlugin,
)


@pytest.fixture
def temp_dir(tmp_path: Path) -> Path:
    """Fixture to provide a temporary directory."""
    return tmp_path


def test_slack_plugin_detect(temp_dir: Path) -> None:
    """Test Slack format detection."""
    plugin = SlackConverterPlugin()

    # Valid Slack JSON
    valid_file = temp_dir / "slack_valid.json"
    with open(valid_file, "w", encoding="utf-8") as f:
        json.dump([{"ts": "1620000000.000001", "user": "U123", "text": "Hello"}], f)

    # Invalid Slack JSON (dict instead of list)
    invalid_file = temp_dir / "slack_invalid.json"
    with open(invalid_file, "w", encoding="utf-8") as f:
        json.dump({"ts": "1620000000.000001", "user": "U123", "text": "Hello"}, f)

    # Non-json file
    txt_file = temp_dir / "slack.txt"
    txt_file.write_text("Hello World")

    assert plugin.detect(valid_file) is True
    assert plugin.detect(invalid_file) is False
    assert plugin.detect(txt_file) is False


def test_slack_plugin_convert(temp_dir: Path) -> None:
    """Test Slack conversion logic."""
    plugin = SlackConverterPlugin()

    file_path = temp_dir / "slack.json"
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(
            [
                {"ts": "1620000000.000000", "user": "U123", "text": "Hello"},
                {"ts": "invalid_ts", "username": "John", "text": "Hi"},
                {"text": "No user or ts"},
            ],
            f,
        )

    results = plugin.convert(file_path)
    assert len(results) == 3
    assert results[0]["author"] == "U123"
    assert results[0]["content"] == "Hello"
    assert results[0]["source"] == "Slack"
    # Unix 1620000000 in UTC is 2021-05-03T00:00:00+00:00
    assert "2021-05-03" in results[0]["timestamp"]

    assert results[1]["author"] == "John"
    assert results[1]["timestamp"] == "invalid_ts"

    assert results[2]["author"] == "System"
    assert results[2]["content"] == "No user or ts"


def test_google_takeout_detect(temp_dir: Path) -> None:
    """Test Google Takeout detection."""
    plugin = GoogleTakeoutConverterPlugin()

    # Location History format
    loc_file = temp_dir / "takeout_loc.json"
    with open(loc_file, "w", encoding="utf-8") as f:
        json.dump({"locations": []}, f)

    # Semantic format
    semantic_file = temp_dir / "takeout_sem.json"
    with open(semantic_file, "w", encoding="utf-8") as f:
        json.dump({"timelineObjects": []}, f)

    # Wrong format
    other_file = temp_dir / "other.json"
    with open(other_file, "w", encoding="utf-8") as f:
        json.dump({"other": 123}, f)

    assert plugin.detect(loc_file) is True
    assert plugin.detect(semantic_file) is True
    assert plugin.detect(other_file) is False


def test_google_takeout_convert_locations(temp_dir: Path) -> None:
    """Test Location History conversion."""
    plugin = GoogleTakeoutConverterPlugin()
    file_path = temp_dir / "loc.json"

    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(
            {
                "locations": [
                    {
                        "timestampMs": "1620000000000",
                        "latitudeE7": 377749290,
                        "longitudeE7": -1224194160,
                        "accuracy": 15,
                    }
                ]
            },
            f,
        )

    results = plugin.convert(file_path)
    assert len(results) == 1
    assert "2021-05-03" in results[0]["timestamp"]
    assert results[0]["source"] == "Google Takeout Location History"
    assert results[0]["author"] == "Location Sensor"
    assert "37.774929" in results[0]["content"]
    assert "-122.419416" in results[0]["content"]


def test_google_takeout_convert_semantic(temp_dir: Path) -> None:
    """Test Semantic Location History conversion."""
    plugin = GoogleTakeoutConverterPlugin()
    file_path = temp_dir / "sem.json"

    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(
            {
                "timelineObjects": [
                    {
                        "placeVisit": {
                            "location": {
                                "latitudeE7": 377749290,
                                "longitudeE7": -1224194160,
                                "name": "Golden Gate Bridge",
                            },
                            "duration": {"startTimestampMs": "1620000000000"},
                        }
                    },
                    {
                        "activitySegment": {
                            "activityType": "WALKING",
                            "distance": 500,
                            "duration": {"startTimestampMs": "1620001000000"},
                        }
                    },
                ]
            },
            f,
        )

    results = plugin.convert(file_path)
    assert len(results) == 2
    assert "Golden Gate Bridge" in results[0]["content"]
    assert "37.774929" in results[0]["content"]
    assert results[0]["source"] == "Google Takeout Semantic Location"

    assert "WALKING" in results[1]["content"]
    assert "500m" in results[1]["content"]
    assert results[1]["source"] == "Google Takeout Activity Segment"


def test_whatsapp_detect(temp_dir: Path) -> None:
    """Test WhatsApp format detection."""
    plugin = WhatsappConverterPlugin()

    file_dash = temp_dir / "wa_dash.txt"
    file_dash.write_text("15/01/2021, 10:24 - John Doe: Hello")

    file_bracket = temp_dir / "wa_bracket.txt"
    file_bracket.write_text("[15/01/2021, 10:24:00] John Doe: Hello")

    file_colon = temp_dir / "wa_colon.txt"
    file_colon.write_text("15/01/2021, 10:24: John Doe: Hello")

    file_invalid = temp_dir / "invalid.txt"
    file_invalid.write_text("Just a normal text file\nNothing to see here")

    assert plugin.detect(file_dash) is True
    assert plugin.detect(file_bracket) is True
    assert plugin.detect(file_colon) is True
    assert plugin.detect(file_invalid) is False


def test_whatsapp_convert(temp_dir: Path) -> None:
    """Test WhatsApp conversion logic."""
    plugin = WhatsappConverterPlugin()
    file_path = temp_dir / "wa.txt"
    file_path.write_text(
        "15/01/2021, 10:24 - John Doe: Hello\n"
        "How are you?\n"
        "[16/01/2021, 11:30:15] Alice: I am good.\n"
        "17/01/2021, 12:00: Bob: Test message"
    )

    results = plugin.convert(file_path)
    assert len(results) == 3

    assert results[0]["timestamp"] == "15/01/2021 10:24"
    assert results[0]["author"] == "John Doe"
    assert results[0]["content"] == "Hello\nHow are you?"

    assert results[1]["timestamp"] == "16/01/2021 11:30:15"
    assert results[1]["author"] == "Alice"
    assert results[1]["content"] == "I am good."

    assert results[2]["timestamp"] == "17/01/2021 12:00"
    assert results[2]["author"] == "Bob"
    assert results[2]["content"] == "Test message"


def test_auto_detect(temp_dir: Path) -> None:
    """Test auto-detect utility function."""
    # Slack
    slack_file = temp_dir / "slack.json"
    with open(slack_file, "w", encoding="utf-8") as f:
        json.dump([{"ts": "123", "text": "hi"}], f)
    assert auto_detect_plugin(slack_file) == "slack"

    # WhatsApp
    wa_file = temp_dir / "wa.txt"
    wa_file.write_text("15/01/2021, 10:24 - John: Hi")
    assert auto_detect_plugin(wa_file) == "whatsapp"

    # Unknown
    unknown_file = temp_dir / "unknown.json"
    unknown_file.write_text("{}")
    assert auto_detect_plugin(unknown_file) == ""


def test_cli_execution_json(temp_dir: Path) -> None:
    """Test CLI execution and writing JSON."""
    input_file = temp_dir / "slack.json"
    with open(input_file, "w", encoding="utf-8") as f:
        json.dump([{"ts": "1620000000.000000", "user": "U123", "text": "Hello"}], f)

    output_file = temp_dir / "output.json"

    test_args = [
        "universal_export_converter",
        str(input_file),
        "-o",
        str(output_file),
        "-f",
        "json",
    ]

    with patch.object(sys, "argv", test_args):
        main()

    assert output_file.is_file()
    with open(output_file, "r", encoding="utf-8") as f:
        out_data = json.load(f)

    assert len(out_data) == 1
    assert out_data[0]["author"] == "U123"
    assert out_data[0]["content"] == "Hello"


def test_cli_execution_csv(temp_dir: Path) -> None:
    """Test CLI execution and writing CSV."""
    input_file = temp_dir / "slack.json"
    with open(input_file, "w", encoding="utf-8") as f:
        json.dump([{"ts": "1620000000.000000", "user": "U123", "text": "Hello"}], f)

    output_file = temp_dir / "output.csv"

    test_args = [
        "universal_export_converter",
        str(input_file),
        "-o",
        str(output_file),
    ]

    with patch.object(sys, "argv", test_args):
        main()

    assert output_file.is_file()
    with open(output_file, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    assert len(rows) == 1
    assert rows[0]["author"] == "U123"
    assert rows[0]["content"] == "Hello"


def test_cli_invalid_file() -> None:
    """Test CLI behavior with non-existent input file."""
    test_args = ["universal_export_converter", "does_not_exist.json"]
    with patch.object(sys, "argv", test_args), pytest.raises(SystemExit) as exc:
        main()
    assert exc.value.code == 1


def test_cli_to_stdout_json(temp_dir: Path, capsys) -> None:
    """Test CLI output redirection to stdout in JSON format."""
    input_file = temp_dir / "slack.json"
    with open(input_file, "w", encoding="utf-8") as f:
        json.dump([{"ts": "1620000000.000000", "user": "U123", "text": "Hello"}], f)

    test_args = ["universal_export_converter", str(input_file), "-f", "json"]
    with patch.object(sys, "argv", test_args):
        main()

    captured = capsys.readouterr()
    data = json.loads(captured.out)
    assert len(data) == 1
    assert data[0]["author"] == "U123"


def test_cli_to_stdout_csv(temp_dir: Path, capsys) -> None:
    """Test CLI output redirection to stdout in CSV format."""
    input_file = temp_dir / "slack.json"
    with open(input_file, "w", encoding="utf-8") as f:
        json.dump([{"ts": "1620000000.000000", "user": "U123", "text": "Hello"}], f)

    test_args = ["universal_export_converter", str(input_file), "-f", "csv"]
    with patch.object(sys, "argv", test_args):
        main()

    captured = capsys.readouterr()
    assert "timestamp" in captured.out
    assert "U123" in captured.out
