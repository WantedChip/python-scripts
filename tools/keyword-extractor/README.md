# Keyword Extractor

Extracts key terms and phrases from text documents using term frequency (TF) or TF-IDF weighting with stop-word filtering and N-gram support.

## Features
- Custom or standard English stop-word filtering
- Term Frequency (TF) and TF-IDF extraction modes
- N-gram phrase extraction (unigrams, bigrams, trigrams)
- Configurable top-N keyword limit
- Export keyword rankings in formatted text or JSON

## Usage

```bash
# Extract top 10 keywords using TF-IDF
python main.py document.txt --top 10 --method tfidf

# Extract top 5 bigram keywords using frequency
python main.py document.txt --ngram 2 --top 5 --json
```
