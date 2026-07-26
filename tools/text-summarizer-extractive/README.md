# Extractive Text Summarizer

Generates extractive summaries by scoring and selecting the most important sentences in a text document using word frequency analysis while retaining original sequence order.

## Features
- Sentence tokenization handling standard punctuation and line breaks
- Frequency-weighted sentence scoring
- Configurable target length ratio (e.g. 0.3 for 30%) or exact sentence count
- Original sentence flow preservation in final summary

## Usage

```bash
# Summarize to 30% of original length
python main.py document.txt --ratio 0.3

# Summarize to top 3 sentences
python main.py document.txt --sentences 3
```
