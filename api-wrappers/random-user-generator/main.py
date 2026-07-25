"""Random User Generator.

Generates fake user profiles for testing via the Random User Generator API
(randomuser.me). Supports nationality & gender filtering, seed configuration,
and CSV/JSON dataset export.
"""

import argparse
import csv
import json
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional, cast


def fetch_random_users(
    count: int = 10,
    nationality: Optional[str] = None,
    gender: Optional[str] = None,
    seed: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Fetch raw user data from randomuser.me API.

    Args:
        count: Number of user profiles to request (1 to 500).
        nationality: Comma-separated ISO country codes (e.g. 'us,gb,de,fr').
        gender: Gender filter ('male' or 'female').
        seed: Random seed string for reproducible results.

    Returns:
        List of raw user objects from API.

    Raises:
        ValueError: If input arguments are out of range.
        RuntimeError: On HTTP or network errors.
    """
    if count < 1 or count > 500:
        raise ValueError("Count must be between 1 and 500.")

    params: Dict[str, Any] = {"results": count}
    if nationality:
        params["nat"] = nationality.strip().lower()
    if gender:
        params["gender"] = gender.strip().lower()
    if seed:
        params["seed"] = seed.strip()

    query_str = urllib.parse.urlencode(params)
    url = f"https://randomuser.me/api/?{query_str}"

    req = urllib.request.Request(
        url,
        headers={"User-Agent": "RandomUserGenerator/1.0 (Python)"},
    )

    try:
        with urllib.request.urlopen(req, timeout=12) as response:  # nosec B310
            if response.status == 200:
                data = json.loads(response.read().decode("utf-8"))
                return cast(List[Dict[str, Any]], data.get("results", []))
            raise RuntimeError(f"HTTP Status {response.status}")
    except urllib.error.HTTPError as err:
        raise RuntimeError(f"HTTP Error {err.code}: {err.reason}") from err
    except urllib.error.URLError as err:
        raise RuntimeError(f"Network error: {err.reason}") from err


def parse_user_profiles(raw_users: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Parse raw user API dicts into standardized profile dicts.

    Args:
        raw_users: List of raw user profile dicts returned by API.

    Returns:
        List of parsed user profile dicts.
    """
    # pylint: disable=too-many-locals
    profiles: List[Dict[str, Any]] = []
    for user in raw_users:
        name = user.get("name", {})
        title = name.get("title", "")
        first = name.get("first", "")
        last = name.get("last", "")
        full_name = f"{first} {last}".strip()

        loc = user.get("location", {})
        street_data = loc.get("street", {})
        if isinstance(street_data, dict):
            street = (
                f"{street_data.get('number', '')} {street_data.get('name', '')}".strip()
            )
        else:
            street = str(street_data)

        city = loc.get("city", "")
        state = loc.get("state", "")
        country = loc.get("country", "")
        postcode = str(loc.get("postcode", ""))

        login = user.get("login", {})
        dob = user.get("dob", {})

        profiles.append(
            {
                "title": title,
                "first_name": first,
                "last_name": last,
                "full_name": full_name,
                "gender": user.get("gender", ""),
                "email": user.get("email", ""),
                "username": login.get("username", ""),
                "phone": user.get("phone", ""),
                "cell": user.get("cell", ""),
                "street": street,
                "city": city,
                "state": state,
                "country": country,
                "postcode": postcode,
                "age": dob.get("age"),
                "dob": dob.get("date", "")[:10] if dob.get("date") else "",
            }
        )
    return profiles


def export_csv(profiles: List[Dict[str, Any]], dest_path: Path) -> None:
    """Export profiles list to CSV file.

    Args:
        profiles: List of parsed profile dicts.
        dest_path: Destination file path.
    """
    if not profiles:
        return

    dest_path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = list(profiles[0].keys())

    with open(dest_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(profiles)


def main() -> None:
    """CLI entry point for Random User Generator."""
    parser = argparse.ArgumentParser(
        description=(
            "Generate fake mock user profiles for testing using randomuser.me API."
        )
    )
    parser.add_argument(
        "-n",
        "--count",
        type=int,
        default=10,
        help="Number of user profiles to generate (1-500, default: 10).",
    )
    parser.add_argument(
        "--nat",
        help="Nationality filter (comma-separated ISO codes: us,gb,de,fr,ca,au).",
    )
    parser.add_argument(
        "--gender",
        choices=["male", "female"],
        help="Filter user profiles by gender.",
    )
    parser.add_argument(
        "--seed",
        help="Seed string for reproducible user data generation.",
    )
    parser.add_argument(
        "-f",
        "--format",
        choices=["json", "csv"],
        default="json",
        help="Output dataset format: json or csv (default: json).",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        help="File path to save the generated CSV/JSON mock dataset.",
    )

    args = parser.parse_args()

    try:
        raw_users = fetch_random_users(
            count=args.count,
            nationality=args.nat,
            gender=args.gender,
            seed=args.seed,
        )
        profiles = parse_user_profiles(raw_users)

        if args.format == "csv":
            if args.output:
                export_csv(profiles, args.output)
                print(
                    f"Successfully generated and exported {len(profiles)} "
                    f"profiles to {args.output}"
                )
            else:
                # Print CSV to stdout if no output file specified
                if profiles:
                    writer = csv.DictWriter(
                        sys.stdout, fieldnames=list(profiles[0].keys())
                    )
                    writer.writeheader()
                    writer.writerows(profiles)
        else:
            json_output = json.dumps(profiles, indent=2)
            if args.output:
                args.output.parent.mkdir(parents=True, exist_ok=True)
                with open(args.output, "w", encoding="utf-8") as f:
                    f.write(json_output)
                print(
                    f"Successfully generated and exported {len(profiles)} "
                    f"profiles to {args.output}"
                )
            else:
                print(json_output)

    except Exception as err:  # pylint: disable=broad-exception-caught
        print(f"Error: {err}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
