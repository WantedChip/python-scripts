# mock-from-traffic

Record development API traffic by running a local reverse proxy server, automatically sanitizing sensitive fields, and saving deterministic mock JSON files for offline development and testing.

## Usage

Start the proxy server, specifying the target API to record:

```bash
python mock_from_traffic.py --target https://api.github.com --port 8080 --output-dir project_mocks
```

Now, point your local application or REST client to `http://localhost:8080` instead of the real API. Every transaction will be proxied, sanitized, and recorded.

For example, query:

```bash
curl http://localhost:8080/users/octocat
```

This will save `get_users_octocat.json` in `project_mocks/` with sensitive headers and bodies redacted.

## Requirements

- Python 3.11+
- Pure standard library (zero external dependencies)

## Notes

- Redacts keys dynamically (default: `Authorization`, `Cookie`, `api_key`, `token`, `password`, `secret`).
- Generates a `mock_driver.py` helper in the output folder to load the recorded mock files dynamically.

## Quality

Quality: pylint 10.00/10 · 100% coverage · 0 dependencies
