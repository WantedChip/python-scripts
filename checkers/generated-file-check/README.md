# Generated File Check Tool

`generated-file-check` detects generated artifacts (e.g. OpenAPI code, protobuf files, schema diagrams, compiled assets) committed to Git that no longer match their source files.

## Usage

```bash
python main.py --root /path/to/repo --manifest .generated-manifest.json --scan-headers
```

## Manifest Specification (`.generated-manifest.json`)

```json
{
  "mappings": [
    {
      "source": "schema/api.proto",
      "generated": "gen/api.pb.go",
      "command": "protoc --go_out=. {source}",
      "hash": "optional_sha256_hash_here"
    }
  ]
}
```

## Features

- Detects header annotations (`@generated`, `DO NOT EDIT`, `AUTO-GENERATED FILE`).
- Verifies files using SHA-256 hash or by re-executing generator commands in temporary directories.
- Returns non-zero exit code if files are out of sync (ideal for CI pipelines).
