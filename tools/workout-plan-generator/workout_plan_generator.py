"""Workout Plan Generator.

Generates a weekly workout program tailored to a user's goals,
experience level, schedule, and equipment constraints.
"""

# pylint: disable=duplicate-code
import argparse
import json
import random
import sys
from typing import Any, Dict, List, Set, Tuple

# Exercise Database
EXERCISES: List[Dict[str, Any]] = [
    # Squat Movement Pattern
    {
        "name": "Barbell Back Squats",
        "pattern": "squat",
        "equipment": "barbell",
        "difficulty": "intermediate",
    },
    {
        "name": "Dumbbell Goblet Squats",
        "pattern": "squat",
        "equipment": "dumbbells",
        "difficulty": "beginner",
    },
    {
        "name": "Bodyweight Squats",
        "pattern": "squat",
        "equipment": "bodyweight",
        "difficulty": "beginner",
    },
    {
        "name": "Leg Press",
        "pattern": "squat",
        "equipment": "machines",
        "difficulty": "beginner",
    },
    {
        "name": "Bulgarian Split Squats",
        "pattern": "squat",
        "equipment": "dumbbells",
        "difficulty": "intermediate",
    },
    # Hinge Movement Pattern
    {
        "name": "Barbell Deadlifts",
        "pattern": "hinge",
        "equipment": "barbell",
        "difficulty": "intermediate",
    },
    {
        "name": "Romanian Deadlifts (Dumbbells)",
        "pattern": "hinge",
        "equipment": "dumbbells",
        "difficulty": "beginner",
    },
    {
        "name": "Barbell Romanian Deadlifts",
        "pattern": "hinge",
        "equipment": "barbell",
        "difficulty": "intermediate",
    },
    {
        "name": "Kettlebell swings / Dumbbell swings",
        "pattern": "hinge",
        "equipment": "dumbbells",
        "difficulty": "beginner",
    },
    {
        "name": "Glute Bridges (Bodyweight)",
        "pattern": "hinge",
        "equipment": "bodyweight",
        "difficulty": "beginner",
    },
    # Horizontal Push Pattern
    {
        "name": "Barbell Flat Bench Press",
        "pattern": "horizontal_push",
        "equipment": "barbell",
        "difficulty": "intermediate",
    },
    {
        "name": "Dumbbell Flat Bench Press",
        "pattern": "horizontal_push",
        "equipment": "dumbbells",
        "difficulty": "beginner",
    },
    {
        "name": "Push-ups",
        "pattern": "horizontal_push",
        "equipment": "bodyweight",
        "difficulty": "beginner",
    },
    {
        "name": "Chest Press Machine",
        "pattern": "horizontal_push",
        "equipment": "machines",
        "difficulty": "beginner",
    },
    # Vertical Push Pattern
    {
        "name": "Overhead Barbell Press",
        "pattern": "vertical_push",
        "equipment": "barbell",
        "difficulty": "intermediate",
    },
    {
        "name": "Dumbbell Shoulder Press",
        "pattern": "vertical_push",
        "equipment": "dumbbells",
        "difficulty": "beginner",
    },
    {
        "name": "Pike Push-ups",
        "pattern": "vertical_push",
        "equipment": "bodyweight",
        "difficulty": "intermediate",
    },
    # Horizontal Pull Pattern
    {
        "name": "Barbell Bent-Over Rows",
        "pattern": "horizontal_pull",
        "equipment": "barbell",
        "difficulty": "intermediate",
    },
    {
        "name": "One-Arm Dumbbell Rows",
        "pattern": "horizontal_pull",
        "equipment": "dumbbells",
        "difficulty": "beginner",
    },
    {
        "name": "Inverted Rows (Bodyweight)",
        "pattern": "horizontal_pull",
        "equipment": "bodyweight",
        "difficulty": "beginner",
    },
    {
        "name": "Seated Cable Rows",
        "pattern": "horizontal_pull",
        "equipment": "cables",
        "difficulty": "beginner",
    },
    # Vertical Pull Pattern
    {
        "name": "Pull-ups",
        "pattern": "vertical_pull",
        "equipment": "bodyweight",
        "difficulty": "advanced",
    },
    {
        "name": "Chin-ups",
        "pattern": "vertical_pull",
        "equipment": "bodyweight",
        "difficulty": "intermediate",
    },
    {
        "name": "Lat Pulldown Machine",
        "pattern": "vertical_pull",
        "equipment": "machines",
        "difficulty": "beginner",
    },
    # Core Pattern
    {
        "name": "Plank",
        "pattern": "core",
        "equipment": "bodyweight",
        "difficulty": "beginner",
    },
    {
        "name": "Hanging Leg Raises",
        "pattern": "core",
        "equipment": "bodyweight",
        "difficulty": "advanced",
    },
    {
        "name": "Dumbbell Russian Twists",
        "pattern": "core",
        "equipment": "dumbbells",
        "difficulty": "beginner",
    },
    {
        "name": "Cable Crunches",
        "pattern": "core",
        "equipment": "cables",
        "difficulty": "intermediate",
    },
    # Isolation Arms Pattern
    {
        "name": "Dumbbell Bicep Curls",
        "pattern": "isolation_arms",
        "equipment": "dumbbells",
        "difficulty": "beginner",
    },
    {
        "name": "Tricep Rope Pushdowns",
        "pattern": "isolation_arms",
        "equipment": "cables",
        "difficulty": "beginner",
    },
    {
        "name": "Dumbbell Overhead Tricep Extensions",
        "pattern": "isolation_arms",
        "equipment": "dumbbells",
        "difficulty": "beginner",
    },
    {
        "name": "Chin-ups (Arms Focus)",
        "pattern": "isolation_arms",
        "equipment": "bodyweight",
        "difficulty": "intermediate",
    },
    # Isolation Shoulders Pattern
    {
        "name": "Dumbbell Lateral Raises",
        "pattern": "isolation_shoulders",
        "equipment": "dumbbells",
        "difficulty": "beginner",
    },
    {
        "name": "Cable Lateral Raises",
        "pattern": "isolation_shoulders",
        "equipment": "cables",
        "difficulty": "intermediate",
    },
    {
        "name": "Face Pulls",
        "pattern": "isolation_shoulders",
        "equipment": "cables",
        "difficulty": "beginner",
    },
]


def filter_exercises(equipment_set: Set[str], user_level: str) -> List[Dict[str, Any]]:
    """Filters database exercises based on equipment and level.

    Args:
        equipment_set: Set of equipment names available.
        user_level: User difficulty level ('beginner', 'intermediate', 'advanced').

    Returns:
        Filtered list of exercise dictionaries.
    """
    difficulty_ranks = {"beginner": 1, "intermediate": 2, "advanced": 3}
    user_rank = difficulty_ranks.get(user_level.lower(), 2)

    filtered = []
    for ex in EXERCISES:
        # Check equipment. Bodyweight is always available.
        eq_needed = ex["equipment"]
        if eq_needed != "bodyweight" and "full-gym" not in equipment_set:
            if eq_needed not in equipment_set:
                continue

        # Check difficulty rank. Allow exercises up to user difficulty rank.
        ex_rank = difficulty_ranks.get(ex["difficulty"], 2)
        if ex_rank <= user_rank + 1:  # Allow slightly above or equal rank
            filtered.append(ex)

    return filtered


def get_default_sets_reps_rest(goal: str, pattern: str) -> Tuple[int, str, int]:
    """Returns sets, reps, and rest time based on workout goal and movement pattern.

    Args:
        goal: Workout goal.
        pattern: Movement pattern (e.g. 'squat', 'core', 'isolation_arms').

    Returns:
        Tuple of (sets, reps_description_string, rest_time_seconds).
    """
    # pylint: disable=too-many-return-statements
    g = goal.lower()
    # Isolation movements have higher rep ranges and less sets/rest
    is_isolation = pattern.startswith("isolation_") or pattern == "core"

    if g == "strength":
        if is_isolation:
            return 3, "8-12", 60
        return 4, "4-6", 180

    if g == "hypertrophy":
        if is_isolation:
            return 3, "10-15", 60
        return 4, "8-12", 90

    if g == "endurance":
        return 3, "15-20", 45

    # Default/Fat Loss
    if is_isolation:
        return 3, "12-15", 45
    return 3, "10-12", 60


def pick_exercise(pattern: str, available: List[Dict[str, Any]], used: Set[str]) -> str:
    """Selects an exercise from available list matching pattern, avoiding duplicates.

    Args:
        pattern: Target movement pattern.
        available: Filtered exercises list.
        used: Set of already selected exercise names in this session.

    Returns:
        The name of the picked exercise, or a fallback string if none found.
    """
    matches = [ex for ex in available if ex["pattern"] == pattern]
    # Filter out already used exercises to avoid repeating them in the same workout
    unused = [ex for ex in matches if ex["name"] not in used]

    if unused:
        picked = random.choice(unused)  # nosec B311 - non-cryptographic choice
        used.add(picked["name"])
        return str(picked["name"])
    if matches:
        # Fallback to allow reuse if we ran out of unique exercises
        picked = random.choice(matches)  # nosec B311 - non-cryptographic choice
        return str(picked["name"])

    # Generic fallback based on pattern
    fallback_map = {
        "squat": "Squats (Bodyweight / Goblet)",
        "hinge": "Hip Hinges / Glute Bridges",
        "horizontal_push": "Push-ups",
        "vertical_push": "Pike Push-ups / Overhead Press",
        "horizontal_pull": "Rows / Pull-ups",
        "vertical_pull": "Lat Pulldowns / Chin-ups",
        "core": "Plank / Core exercises",
        "isolation_arms": "Arm Curls / Extensions",
        "isolation_shoulders": "Lateral Raises",
    }
    return fallback_map.get(pattern, "General Movement")


def generate_workout_program(
    goal: str, level: str, equipment: str, days: int
) -> Dict[str, Any]:
    """Generates the structured workout plan database.

    Args:
        goal: Workout goal.
        level: Experience level.
        equipment: Comma-separated equipment available.
        days: Days per week training schedule.

    Returns:
        Structured dictionary of the generated plan.
    """
    # pylint: disable=too-many-locals
    # Parse equipment
    eq_list = [e.strip().lower() for e in equipment.split(",") if e.strip()]
    equipment_set = set(eq_list)

    # Filter database
    available = filter_exercises(equipment_set, level)
    used_exercises: Set[str] = set()

    # Determine Split
    # PPL (Push, Pull, Legs) or Upper/Lower or Full Body
    split_days: List[Dict[str, Any]] = []
    if days == 2:
        split_days = [
            {
                "name": "Day 1: Full Body A",
                "patterns": [
                    "squat",
                    "horizontal_push",
                    "horizontal_pull",
                    "core",
                ],
            },
            {
                "name": "Day 2: Full Body B",
                "patterns": [
                    "hinge",
                    "vertical_push",
                    "vertical_pull",
                    "isolation_arms",
                ],
            },
        ]
    elif days == 3:
        split_days = [
            {
                "name": "Day 1: Full Body A",
                "patterns": [
                    "squat",
                    "horizontal_push",
                    "vertical_pull",
                    "core",
                ],
            },
            {
                "name": "Day 2: Full Body B",
                "patterns": [
                    "hinge",
                    "vertical_push",
                    "horizontal_pull",
                    "isolation_arms",
                ],
            },
            {
                "name": "Day 3: Full Body C",
                "patterns": [
                    "squat",
                    "horizontal_push",
                    "vertical_pull",
                    "isolation_shoulders",
                ],
            },
        ]
    elif days == 4:
        split_days = [
            {
                "name": "Day 1: Upper A",
                "patterns": [
                    "horizontal_push",
                    "horizontal_pull",
                    "vertical_push",
                    "isolation_arms",
                ],
            },
            {
                "name": "Day 2: Lower A",
                "patterns": ["squat", "hinge", "core"],
            },
            {
                "name": "Day 3: Upper B",
                "patterns": [
                    "vertical_push",
                    "vertical_pull",
                    "horizontal_push",
                    "isolation_shoulders",
                ],
            },
            {
                "name": "Day 4: Lower B",
                "patterns": ["hinge", "squat", "core"],
            },
        ]
    elif days == 5:
        split_days = [
            {
                "name": "Day 1: Push",
                "patterns": [
                    "horizontal_push",
                    "vertical_push",
                    "isolation_shoulders",
                ],
            },
            {
                "name": "Day 2: Pull",
                "patterns": [
                    "horizontal_pull",
                    "vertical_pull",
                    "isolation_arms",
                ],
            },
            {
                "name": "Day 3: Legs",
                "patterns": ["squat", "hinge", "core"],
            },
            {
                "name": "Day 4: Upper",
                "patterns": [
                    "horizontal_push",
                    "vertical_pull",
                    "vertical_push",
                    "horizontal_pull",
                ],
            },
            {
                "name": "Day 5: Lower",
                "patterns": ["hinge", "squat", "core"],
            },
        ]
    else:  # 6 days PPL x2
        split_days = [
            {
                "name": "Day 1: Push A",
                "patterns": [
                    "horizontal_push",
                    "vertical_push",
                    "isolation_shoulders",
                ],
            },
            {
                "name": "Day 2: Pull A",
                "patterns": [
                    "horizontal_pull",
                    "vertical_pull",
                    "isolation_arms",
                ],
            },
            {
                "name": "Day 3: Legs A",
                "patterns": ["squat", "hinge", "core"],
            },
            {
                "name": "Day 4: Push B",
                "patterns": [
                    "vertical_push",
                    "horizontal_push",
                    "isolation_shoulders",
                ],
            },
            {
                "name": "Day 5: Pull B",
                "patterns": [
                    "vertical_pull",
                    "horizontal_pull",
                    "isolation_arms",
                ],
            },
            {
                "name": "Day 6: Legs B",
                "patterns": ["hinge", "squat", "core"],
            },
        ]

    days_plan = []
    for day in split_days:
        day_exercises = []
        for pat in day["patterns"]:
            ex_name = pick_exercise(pat, available, used_exercises)
            sets, reps, rest = get_default_sets_reps_rest(goal, pat)
            day_exercises.append(
                {
                    "exercise": ex_name,
                    "pattern": pat,
                    "sets": sets,
                    "reps": reps,
                    "rest_seconds": rest,
                }
            )
        days_plan.append({"name": day["name"], "exercises": day_exercises})

    plan = {
        "metadata": {
            "goal": goal,
            "level": level,
            "equipment": list(equipment_set),
            "days_per_week": days,
        },
        "program": days_plan,
        "tips": [
            "Warm up for 5-10 minutes with light cardio and dynamic stretches "
            "before each session.",
            "Progressive Overload: Aim to increase the weight or reps slightly "
            "every week to continue progress.",
            "Focus on form over weight to minimize injury risk.",
            "Ensure 48 hours of rest between targeting the same muscle group.",
        ],
    }
    return plan


def format_plan_markdown(plan: Dict[str, Any]) -> str:
    """Formats the workout program dictionary as Markdown.

    Args:
        plan: Program dictionary.

    Returns:
        Formatted markdown string.
    """
    meta = plan["metadata"]
    md = []
    md.append("# Personalized Weekly Workout Program")
    md.append("")
    md.append(
        f"**Goal**: {meta['goal'].title()} | "
        f"**Level**: {meta['level'].title()} | "
        f"**Days/Week**: {meta['days_per_week']}"
    )
    md.append(f"**Equipment Available**: {', '.join(meta['equipment'])}")
    md.append("")
    md.append("---")
    md.append("")

    for day in plan["program"]:
        md.append(f"## {day['name']}")
        md.append("")
        md.append("| Exercise | Sets | Reps | Rest | Focus/Pattern |")
        md.append("| :--- | :---: | :---: | :---: | :--- |")
        for ex in day["exercises"]:
            rest_str = (
                f"{ex['rest_seconds']}s"
                if ex["rest_seconds"] < 60
                else f"{ex['rest_seconds'] // 60}m"
            )
            md.append(
                f"| {ex['exercise']} | {ex['sets']} | {ex['reps']} | {rest_str} | "
                f"{ex['pattern'].replace('_', ' ').title()} |"
            )
        md.append("")

    md.append("---")
    md.append("")
    md.append("## Training Tips")
    for tip in plan["tips"]:
        md.append(f"- {tip}")

    return "\n".join(md)


def main() -> None:
    """CLI entry point for workout generator."""
    parser = argparse.ArgumentParser(
        description=(
            "Generate a personalized workout program based on "
            "fitness goals and equipment."
        )
    )
    parser.add_argument(
        "-g",
        "--goal",
        choices=["strength", "hypertrophy", "endurance", "fat-loss"],
        default="hypertrophy",
        help="Workout goal (default: hypertrophy).",
    )
    parser.add_argument(
        "-l",
        "--level",
        choices=["beginner", "intermediate", "advanced"],
        default="beginner",
        help="Experience level (default: beginner).",
    )
    parser.add_argument(
        "-e",
        "--equipment",
        default="full-gym",
        help=(
            "Comma-separated equipment (e.g. bodyweight, dumbbells, barbell) "
            "or 'full-gym'."
        ),
    )
    parser.add_argument(
        "-d",
        "--days",
        type=int,
        choices=[2, 3, 4, 5, 6],
        default=3,
        help="Active days per week (2 to 6, default 3).",
    )
    parser.add_argument(
        "--format",
        choices=["markdown", "json"],
        default="markdown",
        help="Output plan format (default: markdown).",
    )
    parser.add_argument("-o", "--output", help="Write plan to file instead of stdout.")

    args = parser.parse_args()

    plan = generate_workout_program(args.goal, args.level, args.equipment, args.days)

    if args.format == "json":
        output_str = json.dumps(plan, indent=2)
    else:
        output_str = format_plan_markdown(plan)

    if args.output:
        try:
            with open(args.output, "w", encoding="utf-8") as file:
                file.write(output_str)
            print(f"Workout program written successfully to {args.output}")
        except IOError as err:
            print(f"Error saving file: {err}", file=sys.stderr)
            sys.exit(1)
    else:
        print(output_str)


if __name__ == "__main__":
    main()
