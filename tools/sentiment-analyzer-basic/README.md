# Basic Sentiment Analyzer

A rule-based sentiment analysis script that evaluates positive, negative, and neutral scores in text using lexicon matching and negation handling.

## Features
- Lexicon wordlist based scoring
- Handles common negators (e.g. "not good", "never great")
- Overall sentiment classification (`Positive`, `Negative`, `Neutral`)
- Sentiment breakdown output with matching words
- Custom lexicon JSON file support

## Usage

```bash
# Analyze a text string
python main.py --text "This product is fantastic and works amazingly well!"

# Analyze text from a file with JSON output
python main.py --file review.txt --json
```
