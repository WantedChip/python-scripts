# Recipe Scraper

Parses cooking web pages and HTML files to extract structured recipe data (title, ingredients list, quantities, cooking durations, and step-by-step instructions) into clean Markdown or JSON format.

## Features

- **Schema.org/Recipe JSON-LD Parsing**: Automatically locates `<script type="application/ld+json">` elements and parses structured Recipe schema, including nested `HowToStep` and `HowToSection` objects.
- **ISO 8601 Duration Parser**: Converts durations like `PT1H30M` to human-readable strings like `1 hr 30 mins`.
- **HTML Tag Heuristics**: Fallback scraper for standard recipe HTML structures.
- **Multiple Exports**: Markdown recipe cards, structured JSON, or both.

## Usage

```bash
# Extract recipe from URL and print Markdown summary
python main.py https://example.com/recipe

# Parse local HTML file and export to JSON and Markdown
python main.py sample_recipe.html --format both -o output_recipe
```

## Running Tests

```bash
python -m unittest discover -s tests
```
