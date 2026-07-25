# Weather Scraper CLI

A Python CLI tool to fetch and format current weather conditions and forecasts for cities or coordinates worldwide using Open-Meteo public APIs.

## Features
- **Zero API Key Requirement**: Uses free public geocoding & weather endpoints.
- **City & Coordinate Support**: Lookup by city name or exact latitude/longitude.
- **Unit Customization**: Support for Celsius (°C) and Fahrenheit (°F).
- **Formatted Terminal Display**: Displays weather metrics in an ASCII card view.
- **JSON Export**: Output raw JSON reports for downstream processing.

## Usage

```bash
# Get weather for London
python main.py London

# Get weather in Fahrenheit
python main.py "New York" -u fahrenheit

# Use explicit coordinates
python main.py --lat 48.8566 --lon 2.3522

# Export to JSON file
python main.py Tokyo --json -o tokyo_weather.json
```

## Running Tests

```bash
python -m unittest discover -s tests
```
