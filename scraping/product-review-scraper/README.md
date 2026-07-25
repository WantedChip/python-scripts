# Product Review Scraper

Extracts product reviews (numerical star rating, author name, publication date, review title, body text, verified purchase indicator) from HTML web pages or JSON-LD review structures, calculates rating distribution statistics, and exports structured CSV or JSON files.

## Features

- **Schema.org Review Extraction**: Parses `<script type="application/ld+json">` for `Review` and `Product` object graphs.
- **Rating Distribution Analytics**: Calculates overall count, mean star rating, 1-to-5 star rating distribution counts, and percentage of verified purchases.
- **Text Normalization**: Cleans HTML tags, unescapes entities, and standardizes whitespace for sentiment analysis pipelines.
- **CSV & JSON Export**: Generates dataset exports for data science or machine learning workflows.

## Usage

```bash
# Extract reviews from URL and print JSON summary
python main.py https://example.com/product/reviews

# Parse local HTML file and export to CSV
python main.py product_page.html --format csv -o reviews.csv

# Export both CSV and JSON with stats
python main.py product_page.html --format all -o output_reviews
```

## Running Tests

```bash
python -m unittest discover -s tests
```
