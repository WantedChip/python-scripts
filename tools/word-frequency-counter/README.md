# Word Frequency Counter

A Python text processing CLI utility that tokenizes text files, filters out common stop words, and outputs a sorted word frequency ranking table or JSON payload.

## Features

- **Built-in Stop Words**: Includes a comprehensive set of common English stop words.
- **Custom Stop Words**: Pass a custom file containing additional stop words to ignore.
- **Filtering Options**: Filter words by minimum length or case sensitivity.
- **Multiple Output Formats**: Output as a clean console ranking table, CSV, or structured JSON.

## Usage

```bash
# Display top 10 words in console table
python main.py sample.txt --top 10

# Output top 20 words in JSON format ignoring custom stop words
python main.py article.txt --top 20 --format json --stop-words custom_stop_words.txt
```

## Running Tests

```bash
python -m unittest discover -s tests
```
