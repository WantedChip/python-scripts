# Cat Fact Fetcher

A Python CLI tool to fetch random cat facts from the Cat Facts API (`catfact.ninja`) and accumulate them in a local JSON or Markdown collection with automatic deduplication.

## Features
- Fetches random cat facts via API.
- Deduplicates facts against existing local files before saving.
- Supports both JSON (`.json`) and Markdown (`.md`) storage formats.
- Batch fetch multiple facts in a single run.

## Usage

```bash
# Fetch 1 cat fact and save to default cat_facts.json
python main.py

# Fetch 5 new facts and append to cat_facts.json
python main.py --count 5

# Save facts to a Markdown file
python main.py --count 3 --file my_cat_facts.md
```
