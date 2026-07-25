# Real Estate Listing Scraper

Scrapes property listings (price, location, bedrooms/bathrooms, sqft, features) from HTML or JSON sources.

## Features
- **Price Normalization**: Parses currency symbols (`$`, `EUR`, `GBP`), multipliers (`k`, `M`), and detects rental vs sale pricing.
- **Automated Feature Tagging**: Automatically detects amenities like `pool`, `garage`, `fireplace`, `balcony`, `waterfront`, etc.
- **Flexible Export**: Supports CSV and JSON output formats.
- **Filtering**: Filter properties by price bounds, bedroom count, or specific feature tags.

## Usage

```bash
# Parse local HTML/JSON file and export to CSV
python main.py --file listings.html --format csv --output properties.csv

# Filter for properties under $1,000,000 with at least 3 bedrooms and a pool
python main.py --file listings.json --max-price 1000000 --min-beds 3 --feature pool --format json
```

## Running Tests

```bash
python -m unittest discover tests
```
