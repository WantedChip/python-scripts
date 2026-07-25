import unittest

from main import parse_weather_code, render_weather_summary


class TestWeatherScraper(unittest.TestCase):
    """Unit tests for Weather Scraper CLI."""

    def test_parse_weather_code(self):
        self.assertEqual(parse_weather_code(0), "Clear Sky")
        self.assertEqual(parse_weather_code(3), "Overcast")
        self.assertEqual(parse_weather_code(63), "Moderate Rain")
        self.assertEqual(parse_weather_code(999), "Unknown Weather")

    def test_render_weather_summary(self):
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


if __name__ == "__main__":
    unittest.main()
