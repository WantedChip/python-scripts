# API Response Recorder

Fetch API responses, sanitize sensitive fields (like tokens, passwords, and private headers), and output deterministic test fixtures.

## Usage

Record an endpoint response to a JSON fixture and a companion pytest mock file:
```bash
python src/api_response_recorder/main.py https://api.github.com/users/octocat \
  --output-json fixtures/octocat.json \
  --output-py fixtures/mock_octocat.py
```

Mask custom JSON keys and custom headers:
```bash
python src/api_response_recorder/main.py https://api.github.com/users/octocat \
  --output-json fixtures/octocat.json \
  --mask-key secret_code \
  --mask-header x-custom-token
```

Replace sensitive patterns using regular expressions (e.g. email addresses):
```bash
python src/api_response_recorder/main.py https://api.github.com/users/octocat \
  --output-json fixtures/octocat.json \
  --mask-pattern "[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+"
```

Send headers or post data during record:
```bash
python src/api_response_recorder/main.py https://api.github.com/users/octocat \
  --output-json fixtures/octocat.json \
  --method POST \
  --header "Content-Type: application/json" \
  --data '{"ref": "main"}'
```

## Options

- `url`: Target HTTP/HTTPS endpoint URL to record.
- `--output-json`: Path where the sanitized response details will be written (JSON format).
- `--output-py`: Path where the python helper file containing the pytest mock fixture will be written.
- `--method`: HTTP method to execute during record (default: `GET`).
- `--header`: Key:Value pair to send with the HTTP request. Can be repeated.
- `--data`: Request payload string.
- `--mask-key`: Custom JSON body key to mask. Can be repeated.
- `--mask-header`: Custom header key to mask. Can be repeated.
- `--mask-pattern`: Regular expression pattern to search-and-mask inside text/string values. Can be repeated.

## Quality

Quality: pylint 10.00/10 · 90% coverage · 0 dependencies
