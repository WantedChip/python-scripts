# Dictionary Lookup CLI

Command-line tool to look up word definitions, pronunciations, synonyms, and antonyms using public REST dictionary APIs with offline fallback lexicon support.

## Features
- **REST API Client**: Queries Free Dictionary API (`api.dictionaryapi.dev`) for real-time word lookup.
- **Offline Fallback**: Pre-built offline dictionary lexicon for common English terms when offline or API fails.
- **Rich Output Display**: Shows phonetic pronunciation, parts of speech, definitions, example usage, synonyms, and antonyms.
- **Filtering Options**: Output specifically synonyms, antonyms, or raw JSON formatted response.

## Usage

```bash
# Look up word definition
python main.py lookup python

# Force offline lexicon fallback lookup
python main.py lookup algorithm --offline-only

# Show synonyms only
python main.py lookup fast --synonyms

# Show antonyms only
python main.py lookup fast --antonyms

# Output result in raw JSON format
python main.py lookup code --json
```

## Running Tests

```bash
python -m unittest discover -s tests
```
