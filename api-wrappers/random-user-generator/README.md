# Random User Generator

Generates realistic mock user datasets for testing and prototyping via the Random User Generator API (`randomuser.me`).

## Features

- Generate up to 500 fake user profiles in a single query.
- Filter profiles by nationality (`us`, `gb`, `de`, `fr`, `ca`, `au`, etc.) and gender (`male`, `female`).
- Support for random seed parameters for reproducible test datasets.
- Export datasets to **JSON** or **CSV** files.

## Usage

```bash
# Generate 10 random user profiles in JSON format
python main.py

# Generate 50 female users from US and UK, saved to CSV
python main.py -n 50 --nat us,gb --gender female -f csv -o mock_users.csv

# Generate reproducible dataset using a seed
python main.py -n 5 --seed my_test_seed -o test_users.json
```

## Requirements

Python 3.8+ (Standard Library only).
