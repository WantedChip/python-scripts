# Reading Time Estimator

Estimates the reading time for text files or web page URLs based on custom or default average reading speed (words per minute).

## Features
- File and URL input support
- Automatic HTML tag extraction and fallback handling using standard library `HTMLParser`
- Customizable Words Per Minute (WPM) speed setting (default: 200 WPM)
- Detailed breakdown into word count, total seconds, minutes, and formatted estimate

## Usage

```bash
# Analyze a text file
python main.py sample.txt --wpm 220

# Analyze a web page URL
python main.py https://example.com/article.html --wpm 200
```
