import io
import json
import os
import tempfile
import unittest
import urllib.error
from contextlib import redirect_stdout
from typing import Any, Dict, Optional
from unittest.mock import MagicMock, patch

from main import (
    build_parser,
    fetch_weather,
    geocode_city,
    main,
    parse_weather_code,
    render_weather_summary,
)


def _urlopen_result(payload: Any) -> MagicMock:
    """Build a mock urlopen return value usable as a context manager."""
    resp = MagicMock()
    resp.status = 200
    resp.read.return_value = json.dumps(payload).encode("utf-8")
    resp.__enter__.return_value = resp
    return resp


class TestWeatherScraper(unittest.TestCase):
    """Unit tests for Weather Scraper CLI."""

    def test_parse_weather_code(self) -> None:
        self.assertEqual(parse_weather_code(0), "Clear Sky")
        self.assertEqual(parse_weather_code(3), "Overcast")
        self.assertEqual(parse_weather_code(63), "Moderate Rain")
        self.assertEqual(parse_weather_code(999), "Unknown Weather")

    def test_render_weather_summary(self) -> None:
        sample_weather = {
            "temperature": 22.5,
            "temperature_unit": "°C",
            "wind_speed": 12.0,
            "wind_speed_unit": "km/h",
            "humidity": 60,
            "humidity_unit": "%",
            "condition_code": 0,
            "condition_text": "Clear Sky",
        }
        summary = render_weather_summary("London, United Kingdom", sample_weather)
        self.assertIn("WEATHER REPORT: London, United Kingdom", summary)
        self.assertIn("Condition   : Clear Sky", summary)
        self.assertIn("Temperature : 22.5°C", summary)

    def test_parse_weather_code_accepts_string_digits(self) -> None:
        """Numeric strings are coerced to ints before lookup."""
        self.assertEqual(parse_weather_code("65"), "Heavy Rain")

    def test_geocode_city_success(self) -> None:
        """A successful geocoding response yields lat/lon and a label."""
        payload = {
            "results": [
                {
                    "latitude": 51.5072,
                    "longitude": -0.1276,
                    "name": "London",
                    "country": "United Kingdom",
                }
            ]
        }
        with patch(
            "main.urllib.request.urlopen", return_value=_urlopen_result(payload)
        ):
            result = geocode_city("London")
        assert result is not None
        lat, lon, label = result
        self.assertAlmostEqual(lat, 51.5072)
        self.assertAlmostEqual(lon, -0.1276)
        self.assertEqual(label, "London, United Kingdom")

    def test_geocode_city_without_country(self) -> None:
        """Missing country falls back to the bare city name label."""
        payload = {
            "results": [{"latitude": 35.68, "longitude": 139.69, "name": "Tokyo"}]
        }
        with patch(
            "main.urllib.request.urlopen", return_value=_urlopen_result(payload)
        ):
            result = geocode_city("Tokyo")
        assert result is not None
        self.assertEqual(result[2], "Tokyo")

    def test_geocode_city_no_results(self) -> None:
        """An empty results list resolves to None."""
        with patch(
            "main.urllib.request.urlopen", return_value=_urlopen_result({"results": []})
        ):
            self.assertIsNone(geocode_city("Nowhereville"))

    def test_geocode_city_network_error(self) -> None:
        """Network failures are swallowed and reported as None."""
        with patch(
            "main.urllib.request.urlopen",
            side_effect=urllib.error.URLError("boom"),
        ):
            self.assertIsNone(geocode_city("London"))

    def test_fetch_weather_celsius(self) -> None:
        """Current conditions are normalized into the report dictionary."""
        payload = {
            "current_weather": {
                "temperature": 18.4,
                "windspeed": 9.5,
                "weathercode": 61,
            },
            "hourly": {"relativehumidity_2m": [72, 70]},
        }
        with patch(
            "main.urllib.request.urlopen", return_value=_urlopen_result(payload)
        ):
            data = fetch_weather(51.5, -0.12)
        self.assertEqual(data["temperature"], 18.4)
        self.assertEqual(data["temperature_unit"], "°C")
        self.assertEqual(data["wind_speed"], 9.5)
        self.assertEqual(data["humidity"], 72)
        self.assertEqual(data["condition_text"], "Slight Rain")

    def test_fetch_weather_fahrenheit(self) -> None:
        """Fahrenheit requests switch the reported unit suffix."""
        payload = {
            "current_weather": {
                "temperature": 65.0,
                "windspeed": 4.0,
                "weathercode": 0,
            },
            "hourly": {},
        }
        with patch(
            "main.urllib.request.urlopen", return_value=_urlopen_result(payload)
        ):
            data = fetch_weather(40.7, -74.0, temperature_unit="fahrenheit")
        self.assertEqual(data["temperature_unit"], "°F")
        # Humidity array missing entirely degrades to N/A
        self.assertEqual(data["humidity"], "N/A")


class TestWeatherScraperCli(unittest.TestCase):
    """CLI-level tests for build_parser and main()."""

    def test_build_parser_defaults(self) -> None:
        parser = build_parser()
        args = parser.parse_args([])
        self.assertEqual(args.city, "London")
        self.assertIsNone(args.lat)
        self.assertIsNone(args.lon)
        self.assertEqual(args.units, "celsius")
        self.assertFalse(args.json)
        self.assertIsNone(args.output)

    def _run_main(self, argv: list, weather: Optional[Dict]) -> tuple:
        """Run main() capturing stdout and returning (exit_code, output)."""
        buf = io.StringIO()
        with patch("main.fetch_weather", return_value=weather or {}):
            with redirect_stdout(buf):
                code = main(argv)
        return code, buf.getvalue()

    def test_main_with_coordinates_json_output_file(self) -> None:
        """Coordinate mode skips geocoding and can emit JSON to a file."""
        weather = {
            "temperature": 21.0,
            "temperature_unit": "°C",
            "wind_speed": 5.0,
            "wind_speed_unit": "km/h",
            "humidity": 55,
            "humidity_unit": "%",
            "condition_code": 2,
            "condition_text": "Partly Cloudy",
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            out_path = os.path.join(tmpdir, "report.json")
            buf = io.StringIO()
            with patch("main.fetch_weather", return_value=weather):
                with redirect_stdout(buf):
                    code = main(
                        ["--lat", "48.85", "--lon", "2.35", "--json", "-o", out_path]
                    )
            self.assertEqual(code, 0)
            self.assertIn(f"Report saved to {out_path}", buf.getvalue())
            with open(out_path, encoding="utf-8") as f:
                saved = json.load(f)
            self.assertEqual(saved["location"], "(48.85, 2.35)")
            self.assertEqual(saved["latitude"], 48.85)
            self.assertEqual(saved["weather"]["condition_text"], "Partly Cloudy")

    def test_main_unresolvable_city_returns_error(self) -> None:
        """Geocode failure prints an error to stderr and exits non-zero."""
        import contextlib

        with patch("main.geocode_city", return_value=None):
            with contextlib.redirect_stderr(io.StringIO()) as err:
                code = main(["Atlantis"])
        self.assertEqual(code, 1)
        self.assertIn("Could not resolve coordinates", err.getvalue())

    def test_main_fetch_failure_returns_error(self) -> None:
        """Weather fetch failures surface as exit code 1."""
        import contextlib

        with patch("main.geocode_city", return_value=(1.0, 2.0, "X")):
            with patch(
                "main.fetch_weather",
                side_effect=urllib.error.URLError("down"),
            ):
                with contextlib.redirect_stderr(io.StringIO()) as err:
                    code = main(["Somewhere"])
        self.assertEqual(code, 1)
        self.assertIn("Error fetching weather data", err.getvalue())

    def test_main_success_prints_summary(self) -> None:
        """Default invocation renders the ASCII weather card."""
        weather = {
            "temperature": 10.0,
            "temperature_unit": "°C",
            "wind_speed": 3.0,
            "wind_speed_unit": "km/h",
            "humidity": "N/A",
            "humidity_unit": "%",
            "condition_code": 45,
            "condition_text": "Fog",
        }
        code, out = self._run_main(["--lat", "0", "--lon", "0"], weather)
        self.assertEqual(code, 0)
        self.assertIn("Condition   : Fog", out)
        self.assertIn("Humidity    : N/A%", out)


if __name__ == "__main__":
    unittest.main()
