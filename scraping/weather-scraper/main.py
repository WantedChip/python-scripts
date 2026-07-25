"""Weather Scraper CLI.

Fetches current weather conditions and forecast for a given city or coordinates
using free public APIs (Open-Meteo / wttr.in) without requiring API keys.
"""

# pylint: disable=too-many-branches,too-many-statements
# pylint: disable=too-many-locals,too-many-arguments,too-many-positional-arguments

import argparse
import json
import sys
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional, Tuple

WEATHER_CODES = {
    0: "Clear Sky",
    1: "Mainly Clear",
    2: "Partly Cloudy",
    3: "Overcast",
    45: "Fog",
    48: "Depositing Rime Fog",
    51: "Light Drizzle",
    53: "Moderate Drizzle",
    55: "Dense Drizzle",
    61: "Slight Rain",
    63: "Moderate Rain",
    65: "Heavy Rain",
    71: "Slight Snow",
    73: "Moderate Snow",
    75: "Heavy Snow",
    80: "Slight Rain Showers",
    81: "Moderate Rain Showers",
    82: "Violent Rain Showers",
    95: "Thunderstorm",
}


def geocode_city(city: str) -> Optional[Tuple[float, float, str]]:
    """Geocode city name to (latitude, longitude, formatted_location).

    Args:
        city: Name of the city (e.g., "London", "Tokyo").

    Returns:
        Tuple of (latitude, longitude, location_label) or None if not found.
    """
    encoded_city = urllib.parse.quote(city)
    url = (
        f"https://geocoding-api.open-meteo.com/v1/search?name={encoded_city}"
        "&count=1&language=en&format=json"
    )

    try:
        headers = {"User-Agent": "WeatherScraperCLI/1.0"}
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=10) as resp:  # nosec B310
            data = json.loads(resp.read().decode("utf-8"))
            results = data.get("results")
            if results:
                loc = results[0]
                lat = loc["latitude"]
                lon = loc["longitude"]
                name = loc.get("name", city)
                country = loc.get("country", "")
                label = f"{name}, {country}" if country else name
                return lat, lon, label
    except (
        urllib.error.URLError,
        OSError,
        ValueError,
        KeyError,
        json.JSONDecodeError,
    ):
        pass
    return None


def parse_weather_code(code: int) -> str:
    """Map WMO weather code to readable condition string."""
    return WEATHER_CODES.get(int(code), "Unknown Weather")


def fetch_weather(
    lat: float, lon: float, temperature_unit: str = "celsius"
) -> Dict[str, Any]:
    """Fetch current weather data for lat/lon coordinates.

    Args:
        lat: Latitude.
        lon: Longitude.
        temperature_unit: "celsius" or "fahrenheit".

    Returns:
        Dictionary containing current weather parameters.
    """
    is_f = temperature_unit.lower() == "fahrenheit"
    unit_flag = "fahrenheit" if is_f else "celsius"
    url = (
        f"https://api.open-meteo.com/v1/forecast?"
        f"latitude={lat}&longitude={lon}&current_weather=true"
        f"&hourly=relativehumidity_2m&temperature_unit={unit_flag}"
    )

    headers = {"User-Agent": "WeatherScraperCLI/1.0"}
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=10) as resp:  # nosec B310
        data = json.loads(resp.read().decode("utf-8"))

    current = data.get("current_weather", {})
    hourly = data.get("hourly", {})

    temp = current.get("temperature", 0.0)
    windspeed = current.get("windspeed", 0.0)
    wcode = current.get("weathercode", 0)

    # Approximate humidity from hourly array
    humidity_list = hourly.get("relativehumidity_2m", [])
    humidity = humidity_list[0] if humidity_list else "N/A"

    return {
        "temperature": temp,
        "temperature_unit": "°F" if unit_flag == "fahrenheit" else "°C",
        "wind_speed": windspeed,
        "wind_speed_unit": "km/h",
        "humidity": humidity,
        "humidity_unit": "%",
        "condition_code": wcode,
        "condition_text": parse_weather_code(wcode),
    }


def render_weather_summary(location_label: str, weather_data: Dict[str, Any]) -> str:
    """Format weather data into a terminal summary layout string.

    Args:
        location_label: Formatted location string.
        weather_data: Dictionary of weather parameters.

    Returns:
        Formatted ASCII weather card string.
    """
    t_val = weather_data["temperature"]
    t_unit = weather_data["temperature_unit"]
    temp_str = f"{t_val}{t_unit}"

    h_val = weather_data["humidity"]
    h_unit = weather_data["humidity_unit"]
    humidity_str = f"{h_val}{h_unit}"

    w_val = weather_data["wind_speed"]
    w_unit = weather_data["wind_speed_unit"]
    wind_str = f"{w_val} {w_unit}"

    lines = []
    lines.append("┌" + "─" * 44 + "┐")
    lines.append(f"│ WEATHER REPORT: {location_label:<28} │")
    lines.append("├" + "─" * 44 + "┤")
    lines.append(f"│ Condition   : {weather_data['condition_text']:<28} │")
    lines.append(f"│ Temperature : {temp_str:<28} │")
    lines.append(f"│ Humidity    : {humidity_str:<28} │")
    lines.append(f"│ Wind Speed  : {wind_str:<28} │")
    lines.append("└" + "─" * 44 + "┘")

    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    """Build CLI parser."""
    desc = "Scrape and view current weather report."
    parser = argparse.ArgumentParser(description=desc)
    parser.add_argument(
        "city",
        nargs="?",
        default="London",
        help="City name (e.g., London, Tokyo, New York)",
    )
    parser.add_argument("--lat", type=float, help="Latitude coordinate")
    parser.add_argument("--lon", type=float, help="Longitude coordinate")
    parser.add_argument(
        "-u",
        "--units",
        choices=["celsius", "fahrenheit"],
        default="celsius",
        help="Temperature unit",
    )
    parser.add_argument("--json", action="store_true", help="Output raw JSON report")
    parser.add_argument("-o", "--output", help="Save output to specified file path")
    return parser


def main(args: Optional[List[str]] = None) -> int:
    """CLI entry point for weather scraper."""
    parser = build_parser()
    parsed = parser.parse_args(args)

    if parsed.lat is not None and parsed.lon is not None:
        lat, lon = parsed.lat, parsed.lon
        location_label = f"({lat}, {lon})"
    else:
        print(f"Resolving location for '{parsed.city}'...")
        res = geocode_city(parsed.city)
        if not res:
            err_msg = f"Error: Could not resolve coordinates for city '{parsed.city}'"
            print(err_msg, file=sys.stderr)
            return 1
        lat, lon, location_label = res

    print(f"Fetching weather for {location_label}...")
    try:
        weather_data = fetch_weather(lat, lon, temperature_unit=parsed.units)
    except (urllib.error.URLError, OSError, ValueError) as e:
        print(f"Error fetching weather data: {e}", file=sys.stderr)
        return 1

    result_data = {
        "location": location_label,
        "latitude": lat,
        "longitude": lon,
        "weather": weather_data,
    }

    if parsed.json:
        output_str = json.dumps(result_data, indent=2)
    else:
        output_str = render_weather_summary(location_label, weather_data)

    if parsed.output:
        with open(parsed.output, "w", encoding="utf-8") as f:
            f.write(output_str)
        print(f"Report saved to {parsed.output}")
    else:
        print(output_str)

    return 0


if __name__ == "__main__":
    sys.exit(main())
