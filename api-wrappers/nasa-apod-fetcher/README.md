# NASA APOD Fetcher

Downloads NASA's Astronomy Picture of the Day (APOD) image and saves description metadata as a clean Markdown file.

## Features

- Query today's APOD or any specific historical date (`YYYY-MM-DD`).
- Downloads APOD image files automatically.
- Generates formatted Markdown metadata document including title, date, copyright, explanation, and image preview.
- Supports custom NASA API keys or default `DEMO_KEY`.

## Usage

```bash
# Download today's APOD image and metadata
python main.py

# Download APOD for a specific date
python main.py -d 2024-03-14

# Use custom NASA API Key and custom output directory
python main.py -k YOUR_NASA_API_KEY -o ./my_apod_folder

# Fetch metadata only without downloading image binary
python main.py --no-download
```

## Requirements

Python 3.8+ (Standard Library only).
