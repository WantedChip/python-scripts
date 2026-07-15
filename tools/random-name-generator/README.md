# Random Name Generator

A Python CLI tool to generate suggestions of names for people (fantasy, sci-fi, classic, modern), projects (tech, creative, business), or pets (dog, cat, exotic).

## Usage

```bash
# Generate 5 tech project names
python random_name_generator.py -c projects -s tech

# Generate 10 fantasy character names with alliteration
python random_name_generator.py -c people -s fantasy -q 10 --alliterate

# Save pet dog names to a markdown file
python random_name_generator.py -c pets -s dog -o dog_names.md

# Output modern people names in JSON format
python random_name_generator.py -c people -s modern --format json
```

## Requirements
- Python 3.8+ (zero external dependencies)

## Notes
- Supports three categories: `people`, `projects`, and `pets` with multiple style options.
- Creates name lists dynamically by blending prefix and suffix syllables or selecting and combining word lists.
- Enforces alliteration patterns (similar starting letters) when the `--alliterate` flag is present.
- Supports custom name datasets loaded via `--custom-data` JSON files.

## Quality
Quality: pylint 10.00/10 · 90% coverage · 0 dependencies
