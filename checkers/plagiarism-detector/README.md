# Plagiarism Detector

Compares two text documents and computes similarity metrics (N-gram containment, Jaccard index, and TF-IDF Cosine Similarity) while identifying exact matching snippet phrases.

## Features
- Word N-gram containment and Jaccard similarity scoring
- Vector space Cosine Similarity on word term frequencies
- Extraction and highlighting of matching snippet sequences
- Comprehensive similarity percentage report (JSON or readable terminal output)

## Usage

```bash
# Compare two text files
python main.py doc1.txt doc2.txt --ngram 3

# Export detailed JSON report
python main.py doc1.txt doc2.txt --json
```
