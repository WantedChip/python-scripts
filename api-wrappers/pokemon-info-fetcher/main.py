#!/usr/bin/env python3
"""Pokémon Info Fetcher script.

Looks up Pokémon stats, abilities, types, sprite URLs, and evolution chains
from PokéAPI.
"""

import argparse
import json
import sys
import urllib.error
import urllib.request
from typing import Any, Dict, List, Optional, cast

POKEAPI_BASE_URL = "https://pokeapi.co/api/v2"


def fetch_json(url: str, timeout: int = 10) -> Optional[Dict[str, Any]]:
    """Fetch JSON data from a URL using urllib.

    Args:
        url: Direct API URL to request.
        timeout: Request timeout in seconds.

    Returns:
        Parsed JSON dictionary or None if request fails.
    """
    req = urllib.request.Request(
        url, headers={"User-Agent": "PokemonInfoFetcher/1.0 (Python)"}
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:  # nosec B310
            if response.status == 200:
                return cast(Dict[str, Any], json.loads(response.read().decode("utf-8")))
    except (urllib.error.URLError, urllib.error.HTTPError, json.JSONDecodeError) as err:
        print(f"Error fetching data from {url}: {err}", file=sys.stderr)
    return None


def fetch_pokemon_data(identifier: str) -> Optional[Dict[str, Any]]:
    """Fetch Pokémon information by name or ID.

    Args:
        identifier: Pokémon name or numerical ID.

    Returns:
        Pokémon data dictionary or None if not found.
    """
    clean_id = identifier.strip().lower()
    url = f"{POKEAPI_BASE_URL}/pokemon/{clean_id}"
    return fetch_json(url)


def fetch_evolution_chain(species_url: str) -> List[str]:
    """Fetch evolution chain names starting from a species URL.

    Args:
        species_url: URL to the Pokémon species endpoint.

    Returns:
        List of Pokémon names in the evolution chain.
    """
    species_data = fetch_json(species_url)
    if not species_data or "evolution_chain" not in species_data:
        return []

    evo_url = species_data["evolution_chain"].get("url")
    if not evo_url:
        return []

    evo_data = fetch_json(evo_url)
    if not evo_data or "chain" not in evo_data:
        return []

    chain: List[str] = []

    def extract_names(node: Dict[str, Any]) -> None:
        species_info = node.get("species", {})
        name = species_info.get("name")
        if name:
            chain.append(name.capitalize())
        for evolves_to in node.get("evolves_to", []):
            extract_names(evolves_to)

    extract_names(evo_data["chain"])
    return chain


def format_pokemon_card(data: Dict[str, Any], evolutions: List[str]) -> str:
    """Format Pokémon stats and metadata into a terminal card display.

    Args:
        data: Pokémon API data dictionary.
        evolutions: List of evolution chain names.

    Returns:
        Formatted ASCII string card representation.
    """
    # pylint: disable=too-many-locals
    poke_id = data.get("id", "N/A")
    name = data.get("name", "Unknown").capitalize()
    height = data.get("height", 0) / 10.0  # Decimeters to meters
    weight = data.get("weight", 0) / 10.0  # Hectograms to kg

    types = [
        t.get("type", {}).get("name", "").capitalize() for t in data.get("types", [])
    ]
    abilities = [
        a.get("ability", {}).get("name", "").capitalize()
        for a in data.get("abilities", [])
    ]

    stats_list = data.get("stats", [])
    stats_formatted = []
    for s in stats_list:
        s_name = s.get("stat", {}).get("name", "").replace("-", " ").title()
        s_val = s.get("base_stat", 0)
        stats_formatted.append(f"  • {s_name:<16}: {s_val}")

    sprite = data.get("sprites", {}).get("front_default", "N/A")
    evo_str = " -> ".join(evolutions) if evolutions else "N/A"

    lines = [
        "==================================================",
        f"  POKÉMON STAT CARD: #{poke_id} {name.upper()}",
        "==================================================",
        f"  Name       : {name}",
        f"  ID         : #{poke_id}",
        f"  Type(s)    : {', '.join(types)}",
        f"  Height     : {height} m",
        f"  Weight     : {weight} kg",
        f"  Abilities  : {', '.join(abilities)}",
        "--------------------------------------------------",
        "  BASE STATS:",
        *stats_formatted,
        "--------------------------------------------------",
        f"  Evolutions : {evo_str}",
        f"  Sprite URL : {sprite}",
        "==================================================",
    ]
    return "\n".join(lines)


def export_json(data: Dict[str, Any], evolutions: List[str], filepath: str) -> bool:
    """Export Pokémon data to a JSON file.

    Args:
        data: Pokémon API data dictionary.
        evolutions: Evolution chain list.
        filepath: Target output file path.

    Returns:
        True if export succeeded, False otherwise.
    """
    export_payload = {
        "id": data.get("id"),
        "name": data.get("name"),
        "height_m": data.get("height", 0) / 10.0,
        "weight_kg": data.get("weight", 0) / 10.0,
        "types": [t.get("type", {}).get("name") for t in data.get("types", [])],
        "abilities": [
            a.get("ability", {}).get("name") for a in data.get("abilities", [])
        ],
        "stats": {
            s.get("stat", {}).get("name"): s.get("base_stat")
            for s in data.get("stats", [])
        },
        "evolutions": evolutions,
        "sprite_url": data.get("sprites", {}).get("front_default"),
    }

    try:
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(export_payload, f, indent=2)
        return True
    except OSError as err:
        print(f"Error writing JSON to {filepath}: {err}", file=sys.stderr)
        return False


def main() -> None:
    """Main CLI entrypoint for Pokémon Info Fetcher."""
    parser = argparse.ArgumentParser(
        description="Fetch Pokémon information, stats, and evolutions from PokéAPI."
    )
    parser.add_argument("pokemon", help="Pokémon name or ID (e.g. pikachu, 25)")
    parser.add_argument("--json", "-j", help="Path to export formatted JSON data")
    parser.add_argument(
        "--raw", action="store_true", help="Print raw JSON response from API"
    )

    args = parser.parse_args()

    print(f"Fetching data for '{args.pokemon}'...")
    data = fetch_pokemon_data(args.pokemon)

    if not data:
        print(
            f"Could not find Pokémon '{args.pokemon}'. Please check the name or ID.",
            file=sys.stderr,
        )
        sys.exit(1)

    if args.raw:
        print(json.dumps(data, indent=2))
        return

    species_url = data.get("species", {}).get("url")
    evolutions = fetch_evolution_chain(species_url) if species_url else []

    card = format_pokemon_card(data, evolutions)
    print(card)

    if args.json:
        if export_json(data, evolutions, args.json):
            print(f"Successfully exported data to {args.json}")


if __name__ == "__main__":
    main()
