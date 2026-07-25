# Podcast Episode Scraper

Parses podcast RSS XML feeds to list recent episodes with episode titles, publication dates, descriptions, durations, and direct audio download links.

## Features
- **RSS/XML Parser**: Parses standard RSS 2.0 and iTunes podcast metadata (durations, episode/season tags, enclosure URLs).
- **HTML Cleaning**: Strips unwanted HTML markup from descriptions.
- **Markdown Playlist Export**: Generates clean Markdown documents with direct listening and stream links.
- **Audio Downloader**: Automated local audio file downloader with file name sanitization.

## Usage

```bash
# Parse feed URL and export Markdown playlist
python main.py --feed-url https://example.com/podcast.xml --export-md playlist.md

# Search for specific topic episodes and limit output
python main.py --file podcast.xml --search asyncio --max-episodes 5

# Download recent episode audio files locally
python main.py --file podcast.xml --download --download-dir ./episodes --max-downloads 3
```

## Running Tests

```bash
python -m unittest discover tests
```
