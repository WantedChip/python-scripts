"""Travel Itinerary Planner.

Assembles detailed, customizable day-by-day travel schedules based on
destination, duration, travel style, pace, and budget constraints.
"""

# pylint: disable=duplicate-code
import argparse
import json
import random
import sys
from typing import Any, Dict, List, Optional, Set

# Time ranking for daily sorting
TIME_RANKS: Dict[str, int] = {"morning": 1, "afternoon": 2, "evening": 3}


# Built-in Destinations and Points of Interest (POIs)
DESTINATIONS: Dict[str, List[Dict[str, Any]]] = {
    "tokyo": [
        {
            "name": "Senso-ji Temple (Asakusa)",
            "time": "morning",
            "style": "cultural",
            "budget": "budget",
            "desc": "Tokyo's oldest and most iconic Buddhist temple.",
            "cost_val": 0,
        },
        {
            "name": "Meiji Jingu Shrine & Yoyogi Park",
            "time": "morning",
            "style": "relaxing",
            "budget": "budget",
            "desc": "A serene forested shrine precinct in Shibuya.",
            "cost_val": 0,
        },
        {
            "name": "Shibuya Crossing & Hachiko Statue",
            "time": "afternoon",
            "style": "cultural",
            "budget": "budget",
            "desc": "The world's busiest pedestrian crossing.",
            "cost_val": 0,
        },
        {
            "name": "TeamLab Planets Digital Art Museum",
            "time": "afternoon",
            "style": "adventure",
            "budget": "moderate",
            "desc": "A massive, immersive digital artwork museum.",
            "cost_val": 35,
        },
        {
            "name": "Shinjuku Gyoen National Garden",
            "time": "afternoon",
            "style": "relaxing",
            "budget": "budget",
            "desc": (
                "Beautiful large gardens blending French, English, "
                "and Japanese styles."
            ),
            "cost_val": 5,
        },
        {
            "name": "Sushi Zanmai (Tsukiji)",
            "time": "afternoon",
            "style": "foodie",
            "budget": "moderate",
            "desc": "Incredible fresh sushi directly from the outer market area.",
            "cost_val": 30,
        },
        {
            "name": "Roppongi Hills Observation Deck",
            "time": "evening",
            "style": "relaxing",
            "budget": "moderate",
            "desc": "Stunning outdoor panoramic city views of Tokyo Tower.",
            "cost_val": 15,
        },
        {
            "name": "Omakase Sushi Dinner (Ginza)",
            "time": "evening",
            "style": "foodie",
            "budget": "luxury",
            "desc": "High-end, chef-curated multiple course sushi dining experience.",
            "cost_val": 150,
        },
        {
            "name": "Omoide Yokocho (Shinjuku Memory Lane)",
            "time": "evening",
            "style": "foodie",
            "budget": "budget",
            "desc": "Narrow alleys filled with tiny yakitori stalls and retro charm.",
            "cost_val": 20,
        },
    ],
    "paris": [
        {
            "name": "Eiffel Tower Summit",
            "time": "morning",
            "style": "cultural",
            "budget": "moderate",
            "desc": "Ascend the iconic tower for unparalleled views over Paris.",
            "cost_val": 25,
        },
        {
            "name": "Louvre Museum",
            "time": "afternoon",
            "style": "cultural",
            "budget": "moderate",
            "desc": "The world's largest art museum, home to the Mona Lisa.",
            "cost_val": 17,
        },
        {
            "name": "Seine River Dinner Cruise",
            "time": "evening",
            "style": "relaxing",
            "budget": "luxury",
            "desc": (
                "Gourmet meal on a glass-walled boat sailing past "
                "illuminated monuments."
            ),
            "cost_val": 120,
        },
        {
            "name": "Sacre-Coeur & Montmartre Walk",
            "time": "afternoon",
            "style": "cultural",
            "budget": "budget",
            "desc": (
                "Charming artist neighborhood ending at the "
                "stunning hilltop Basilica."
            ),
            "cost_val": 0,
        },
        {
            "name": "Jardin du Luxembourg",
            "time": "morning",
            "style": "relaxing",
            "budget": "budget",
            "desc": (
                "Stately palace gardens popular with locals for " "sailing model boats."
            ),
            "cost_val": 0,
        },
        {
            "name": "Michelin Star Dining (Le Bistrot)",
            "time": "evening",
            "style": "foodie",
            "budget": "luxury",
            "desc": "Modern French culinary masterpieces and fine wine pairings.",
            "cost_val": 200,
        },
        {
            "name": "Catacombs of Paris",
            "time": "afternoon",
            "style": "adventure",
            "budget": "moderate",
            "desc": "Underground ossuaries holding the remains of six million people.",
            "cost_val": 29,
        },
        {
            "name": "Quartier Latin Crepe Crawl",
            "time": "evening",
            "style": "foodie",
            "budget": "budget",
            "desc": (
                "Sample classic sweet and savory crepes in the "
                "lively student district."
            ),
            "cost_val": 10,
        },
    ],
}


def load_pois(custom_file_path: Optional[str]) -> Dict[str, List[Dict[str, Any]]]:
    """Loads POIs from a custom JSON file or defaults to the built-in database.

    Args:
        custom_file_path: Optional file path to custom JSON file.

    Returns:
        A dictionary mapping destinations to their list of POIs.
    """
    if not custom_file_path:
        return DESTINATIONS

    try:
        with open(custom_file_path, "r", encoding="utf-8") as file:
            data = json.load(file)
            if isinstance(data, dict):
                return data
    except (FileNotFoundError, json.JSONDecodeError, ValueError) as err:
        print(
            f"Warning: Failed to load custom POI file ({err}). "
            "Falling back to built-in database.",
            file=sys.stderr,
        )
    return DESTINATIONS


def get_fallback_pois(destination: str) -> List[Dict[str, Any]]:
    """Generates a dynamic list of mock POIs for unrecognized destinations.

    Args:
        destination: Name of the destination.

    Returns:
        List of generated mock POIs.
    """
    dest_title = destination.title()
    return [
        {
            "name": f"Explore {dest_title} Downtown & Historic Sites",
            "time": "morning",
            "style": "cultural",
            "budget": "budget",
            "desc": "Get oriented with a walking tour of the main square.",
            "cost_val": 0,
        },
        {
            "name": f"Central Park / Gardens of {dest_title}",
            "time": "morning",
            "style": "relaxing",
            "budget": "budget",
            "desc": "Enjoy a peaceful morning walk among local plants and paths.",
            "cost_val": 0,
        },
        {
            "name": f"Famous Local Museum of {dest_title}",
            "time": "afternoon",
            "style": "cultural",
            "budget": "moderate",
            "desc": "Exhibits displaying the rich heritage and history of the region.",
            "cost_val": 15,
        },
        {
            "name": f"{dest_title} Outdoor Guided Excursion",
            "time": "afternoon",
            "style": "adventure",
            "budget": "moderate",
            "desc": "A scenic hike or activity showing local natural landscapes.",
            "cost_val": 40,
        },
        {
            "name": f"Traditional Food Market Tour in {dest_title}",
            "time": "afternoon",
            "style": "foodie",
            "budget": "budget",
            "desc": "Taste local street snacks and discover specialty shops.",
            "cost_val": 12,
        },
        {
            "name": f"Signature Observation Tower of {dest_title}",
            "time": "evening",
            "style": "relaxing",
            "budget": "moderate",
            "desc": "Watch the sunset from the highest point in town.",
            "cost_val": 20,
        },
        {
            "name": f"High-end Culinary Feast in {dest_title}",
            "time": "evening",
            "style": "foodie",
            "budget": "luxury",
            "desc": "Famous local chef's selection dining experience.",
            "cost_val": 100,
        },
        {
            "name": f"{dest_title} Riverside Walk & Bistro Dinner",
            "time": "evening",
            "style": "foodie",
            "budget": "moderate",
            "desc": "Sample standard cuisine alongside the water.",
            "cost_val": 30,
        },
    ]


def build_itinerary(
    destination: str,
    days: int,
    style: str,
    pace: str,
    budget: str,
    custom_data: Optional[str] = None,
) -> Dict[str, Any]:
    """Compiles a travel schedule based on constraints.

    Args:
        destination: Destination name.
        days: Duration in days.
        style: Travel style preference.
        pace: Speed of tour.
        budget: Budget tier limit.
        custom_data: Optional custom JSON database path.

    Returns:
        Structured travel itinerary dictionary.
    """
    # pylint: disable=too-many-arguments,too-many-positional-arguments,too-many-locals
    dest_lower = destination.lower()
    all_dest_data = load_pois(custom_data)

    pois = all_dest_data.get(dest_lower)
    if not pois:
        pois = get_fallback_pois(destination)

    # Filter POIs by budget constraints (allows tier matching)
    budget_map = {
        "budget": {"budget"},
        "moderate": {"budget", "moderate"},
        "luxury": {"budget", "moderate", "luxury"},
    }
    allowed_budgets = budget_map.get(budget.lower(), {"budget", "moderate"})

    filtered_pois = [p for p in pois if p["budget"] in allowed_budgets]
    if not filtered_pois:
        # Safety fallback
        filtered_pois = pois

    # Determine activities count per day based on pace
    pace_counts = {"slow": 1, "moderate": 2, "fast": 3}
    act_per_day = pace_counts.get(pace.lower(), 2)

    # Track used POIs so we don't repeat activities
    used_pois: Set[str] = set()
    program = []
    total_cost = 0

    for i in range(days):
        day_num = i + 1
        day_activities: List[Dict[str, Any]] = []

        # Try to schedule activities by time of day (morning, afternoon, evening)
        for time_slot in ["morning", "afternoon", "evening"]:
            if len(day_activities) >= act_per_day:
                break

            # Find matching unused POIs for this time slot
            matches = [
                p
                for p in filtered_pois
                if p["time"] == time_slot and p["name"] not in used_pois
            ]

            # Style scoring: prioritize POIs matching the chosen style
            if matches:
                style_matches = [p for p in matches if p["style"] == style.lower()]
                # Prioritize style matches, otherwise fallback to slot matches
                candidates = style_matches if style_matches else matches
                selected = random.choice(candidates)  # nosec B311
                used_pois.add(selected["name"])
                day_activities.append(selected)
                total_cost += selected["cost_val"]

        # If we couldn't fill the pace requirement, try matching any time slot
        if len(day_activities) < act_per_day:
            remaining_matches = [p for p in filtered_pois if p["name"] not in used_pois]
            if remaining_matches:
                # Add random activities to satisfy the daily pace limit
                while len(day_activities) < act_per_day and remaining_matches:
                    selected = random.choice(remaining_matches)  # nosec B311
                    used_pois.add(selected["name"])
                    day_activities.append(selected)
                    total_cost += selected["cost_val"]
                    remaining_matches.remove(selected)

        # Sort activities for the day: morning -> afternoon -> evening
        day_activities.sort(key=lambda x: TIME_RANKS.get(x["time"], 2))

        program.append(
            {
                "day": day_num,
                "title": f"Day {day_num}",
                "activities": day_activities,
            }
        )

    return {
        "metadata": {
            "destination": destination.title(),
            "days": days,
            "style": style,
            "pace": pace,
            "budget": budget,
            "total_estimated_cost": total_cost,
        },
        "program": program,
    }


def format_itinerary_markdown(itinerary: Dict[str, Any]) -> str:
    """Formats the travel itinerary as a beautiful Markdown string.

    Args:
        itinerary: Structured itinerary dictionary.

    Returns:
        Formatted markdown document.
    """
    meta = itinerary["metadata"]
    md = []
    md.append(f"# Travel Itinerary: {meta['destination']}")
    md.append("")
    md.append(
        f"**Duration**: {meta['days']} Days | "
        f"**Style**: {meta['style'].title()} | "
        f"**Pace**: {meta['pace'].title()} | "
        f"**Budget**: {meta['budget'].title()}"
    )
    md.append(f"**Total Estimated Activity Cost**: ${meta['total_estimated_cost']}")
    md.append("")
    md.append("---")
    md.append("")

    for day in itinerary["program"]:
        md.append(f"## Day {day['day']}")
        md.append("")
        for act in day["activities"]:
            cost_str = "Free" if act["cost_val"] == 0 else f"${act['cost_val']}"
            md.append(f"### {act['name']} ({act['time'].title()} - {cost_str})")
            md.append(f"- **Focus**: {act['style'].title()}")
            md.append(f"- **Description**: {act['desc']}")
            md.append("")
        md.append("---")

    return "\n".join(md)


def main() -> None:
    """CLI entry point for travel-itinerary-planner."""
    parser = argparse.ArgumentParser(
        description=(
            "Build a day-by-day travel itinerary based on "
            "duration, budget, and style."
        )
    )
    parser.add_argument(
        "-d", "--destination", required=True, help="Destination city or region."
    )
    parser.add_argument(
        "-n",
        "--days",
        type=int,
        default=3,
        help="Number of days (1 to 14, default 3).",
    )
    parser.add_argument(
        "-s",
        "--style",
        choices=["cultural", "adventure", "relaxing", "foodie", "balanced"],
        default="balanced",
        help="Travel style (default: balanced).",
    )
    parser.add_argument(
        "-p",
        "--pace",
        choices=["slow", "moderate", "fast"],
        default="moderate",
        help="Tour pace (default: moderate).",
    )
    parser.add_argument(
        "-b",
        "--budget",
        choices=["budget", "moderate", "luxury"],
        default="moderate",
        help="Budget tier (default: moderate).",
    )
    parser.add_argument(
        "--format",
        choices=["markdown", "json"],
        default="markdown",
        help="Output format (default: markdown).",
    )
    parser.add_argument("-o", "--output", help="Write plan to file instead of stdout.")
    parser.add_argument(
        "--custom-data",
        help="Path to custom JSON file containing POIs dataset.",
    )

    args = parser.parse_args()

    # Constraint check
    if args.days < 1 or args.days > 14:
        print("Error: Days must be between 1 and 14.", file=sys.stderr)
        sys.exit(1)

    itinerary = build_itinerary(
        args.destination,
        args.days,
        args.style,
        args.pace,
        args.budget,
        args.custom_data,
    )

    if args.format == "json":
        output_str = json.dumps(itinerary, indent=2)
    else:
        output_str = format_itinerary_markdown(itinerary)

    if args.output:
        try:
            with open(args.output, "w", encoding="utf-8") as file:
                file.write(output_str)
            print(f"Travel itinerary written successfully to {args.output}")
        except IOError as err:
            print(f"Error saving file: {err}", file=sys.stderr)
            sys.exit(1)
    else:
        print(output_str)


if __name__ == "__main__":
    main()
