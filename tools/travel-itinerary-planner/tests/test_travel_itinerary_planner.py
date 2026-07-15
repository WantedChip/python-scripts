"""Tests for travel_itinerary_planner.py."""

import json
import os
import sys

import pytest

# Add current folder to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# pylint: disable=import-error
from travel_itinerary_planner import (  # noqa: E402
    build_itinerary,
    format_itinerary_markdown,
    get_fallback_pois,
    load_pois,
    main,
)


def test_load_pois(tmp_path: pytest.TempPathFactory) -> None:
    """Tests load_pois function."""
    # Built-in fallback
    pois = load_pois(None)
    assert "tokyo" in pois
    assert len(pois["tokyo"]) > 0

    # Custom valid JSON loading
    custom_data = {
        "test-dest": [
            {
                "name": "Test Place",
                "time": "morning",
                "style": "relaxing",
                "budget": "budget",
                "cost_val": 0,
            }
        ]
    }
    custom_file = tmp_path / "custom.json"
    custom_file.write_text(json.dumps(custom_data), encoding="utf-8")

    loaded = load_pois(str(custom_file))
    assert "test-dest" in loaded
    assert loaded["test-dest"][0]["name"] == "Test Place"

    # Invalid JSON path should fall back to built-ins
    fallback = load_pois("does_not_exist.json")
    assert "tokyo" in fallback


def test_get_fallback_pois() -> None:
    """Tests get_fallback_pois function."""
    fallback_pois = get_fallback_pois("sydney")
    assert len(fallback_pois) > 0
    # Sydney should be embedded in POI names
    assert any("Sydney" in p["name"] for p in fallback_pois)


def test_build_itinerary() -> None:
    """Tests build_itinerary function."""
    # Tokyo, 2 days, foodie, moderate, budget
    itinerary = build_itinerary("tokyo", 2, "foodie", "moderate", "budget")
    assert itinerary["metadata"]["destination"] == "Tokyo"
    assert itinerary["metadata"]["days"] == 2
    assert len(itinerary["program"]) == 2

    # Check pacing and budget limits
    for day in itinerary["program"]:
        assert len(day["activities"]) <= 2
        for act in day["activities"]:
            assert act["budget"] == "budget"  # only budget allowed

    # Test unrecognized destination fallback
    fallback_iti = build_itinerary("berlin", 1, "cultural", "slow", "luxury")
    assert fallback_iti["metadata"]["destination"] == "Berlin"
    assert len(fallback_iti["program"]) == 1


def test_format_itinerary_markdown() -> None:
    """Tests format_itinerary_markdown function."""
    itinerary = build_itinerary("paris", 1, "cultural", "slow", "moderate")
    markdown_str = format_itinerary_markdown(itinerary)
    assert "# Travel Itinerary: Paris" in markdown_str
    assert "**Duration**: 1 Days" in markdown_str
    assert "Day 1" in markdown_str
    assert "---" in markdown_str


def test_main_cli(
    tmp_path: pytest.TempPathFactory,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Tests main CLI interface."""
    # Stdout markdown verification
    monkeypatch.setattr(
        sys, "argv", ["travel_itinerary_planner.py", "-d", "tokyo", "-n", "2"]
    )
    main()
    captured = capsys.readouterr()
    assert "# Travel Itinerary: Tokyo" in captured.out
    assert "Day 1" in captured.out

    # Invalid days constraint check
    monkeypatch.setattr(
        sys, "argv", ["travel_itinerary_planner.py", "-d", "tokyo", "-n", "20"]
    )
    with pytest.raises(SystemExit) as exc:
        main()
    assert exc.value.code == 1
    captured = capsys.readouterr()
    assert "Days must be between 1 and 14" in captured.err

    # Save to file verification
    output_file = tmp_path / "trip.md"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "travel_itinerary_planner.py",
            "-d",
            "paris",
            "-o",
            str(output_file),
        ],
    )
    main()
    assert output_file.exists()
    content = output_file.read_text(encoding="utf-8")
    assert "# Travel Itinerary: Paris" in content
    capsys.readouterr()  # Clear buffer

    # Output JSON verification
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "travel_itinerary_planner.py",
            "-d",
            "tokyo",
            "--format",
            "json",
        ],
    )
    main()
    captured = capsys.readouterr()
    data = json.loads(captured.out)
    assert data["metadata"]["destination"] == "Tokyo"
