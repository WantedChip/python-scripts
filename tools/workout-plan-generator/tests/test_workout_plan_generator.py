"""Tests for workout_plan_generator.py."""

import json
import os
import sys

import pytest

# Add current folder to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# pylint: disable=import-error
from workout_plan_generator import (  # noqa: E402
    filter_exercises,
    format_plan_markdown,
    generate_workout_program,
    get_default_sets_reps_rest,
    main,
    pick_exercise,
)


def test_filter_exercises() -> None:
    """Tests filter_exercises function."""
    # Bodyweight only, beginner
    eq_set = {"bodyweight"}
    exercises = filter_exercises(eq_set, "beginner")
    for ex in exercises:
        assert ex["equipment"] == "bodyweight"
        assert ex["difficulty"] in ("beginner", "intermediate")  # allow +1 level

    # Full gym, advanced
    eq_set_full = {"full-gym"}
    exercises_full = filter_exercises(eq_set_full, "advanced")
    # Should include barbell, dumbbells, cables, machines, bodyweight
    equipment_found = {ex["equipment"] for ex in exercises_full}
    assert "barbell" in equipment_found
    assert "dumbbells" in equipment_found
    assert "bodyweight" in equipment_found


def test_get_default_sets_reps_rest() -> None:
    """Tests get_default_sets_reps_rest function."""
    # Strength goal, compound exercise
    assert get_default_sets_reps_rest("strength", "squat") == (4, "4-6", 180)
    # Strength goal, isolation exercise
    assert get_default_sets_reps_rest("strength", "isolation_arms") == (3, "8-12", 60)

    # Hypertrophy goal, compound exercise
    assert get_default_sets_reps_rest("hypertrophy", "squat") == (4, "8-12", 90)

    # Endurance goal
    assert get_default_sets_reps_rest("endurance", "squat") == (3, "15-20", 45)


def test_pick_exercise() -> None:
    """Tests pick_exercise function."""
    available = [
        {"name": "Squats", "pattern": "squat", "equipment": "bodyweight"},
        {"name": "Lunges", "pattern": "squat", "equipment": "bodyweight"},
    ]
    used = set()

    ex1 = pick_exercise("squat", available, used)
    assert ex1 in ("Squats", "Lunges")
    assert ex1 in used

    ex2 = pick_exercise("squat", available, used)
    assert ex2 in ("Squats", "Lunges")
    assert ex2 != ex1  # should pick the other unused one

    # Test fallback
    assert pick_exercise("non-existent-pattern", [], used) == "General Movement"


def test_generate_workout_program() -> None:
    """Tests generate_workout_program function."""
    plan = generate_workout_program(
        "strength", "intermediate", "dumbbells,bodyweight", 3
    )
    assert plan["metadata"]["goal"] == "strength"
    assert plan["metadata"]["level"] == "intermediate"
    assert "dumbbells" in plan["metadata"]["equipment"]
    assert "bodyweight" in plan["metadata"]["equipment"]
    assert len(plan["program"]) == 3

    # Check that exercises use only dumbbells or bodyweight
    for day in plan["program"]:
        assert len(day["exercises"]) > 0
        for ex in day["exercises"]:
            assert "sets" in ex
            assert "reps" in ex
            assert "rest_seconds" in ex


def test_format_plan_markdown() -> None:
    """Tests format_plan_markdown function."""
    plan = generate_workout_program("hypertrophy", "beginner", "bodyweight", 2)
    markdown_str = format_plan_markdown(plan)
    assert "# Personalized Weekly Workout Program" in markdown_str
    assert "**Goal**: Hypertrophy" in markdown_str
    assert "**Level**: Beginner" in markdown_str
    assert "Day 1: Full Body A" in markdown_str
    assert "|" in markdown_str  # should contain table formatting


def test_main_cli(
    tmp_path: pytest.TempPathFactory,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Tests main CLI interface."""
    # Stdout markdown verification
    monkeypatch.setattr(
        sys, "argv", ["workout_plan_generator.py", "-g", "strength", "-d", "4"]
    )
    main()
    captured = capsys.readouterr()
    assert "# Personalized Weekly Workout Program" in captured.out
    assert "**Goal**: Strength" in captured.out
    assert "Day 4: Lower B" in captured.out

    # Save to file verification
    output_file = tmp_path / "plan.md"
    monkeypatch.setattr(
        sys, "argv", ["workout_plan_generator.py", "-o", str(output_file)]
    )
    main()
    assert output_file.exists()
    content = output_file.read_text(encoding="utf-8")
    assert "# Personalized Weekly Workout Program" in content
    capsys.readouterr()  # Clear buffer

    # Save to JSON verification
    monkeypatch.setattr(sys, "argv", ["workout_plan_generator.py", "--format", "json"])
    main()
    captured = capsys.readouterr()
    data = json.loads(captured.out)
    assert data["metadata"]["goal"] == "hypertrophy"
