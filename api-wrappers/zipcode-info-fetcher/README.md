# Zipcode Info Fetcher

A Python CLI tool to look up city, state, country, and geographic coordinates for postal codes around the world using the Zippopotam.us API.

## Features

- Query postal codes by country (default `us`)
- Extract city/place name, state name/abbreviation, latitude, and longitude
- Clean terminal card output format
- Export results to structured JSON files

## Usage

```bash
python main.py 90210
python main.py 90210 --country us
python main.py K1A0B1 --country ca --output ottawa_zip.json
```

## Running Tests

```bash
python -m unittest discover -s tests
```
