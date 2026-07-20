# API Contract Diff

Compare two API specifications (OpenAPI/Swagger JSON or YAML formats) and report client-breaking changes.

## Usage

```bash
python checkers/api-contract-diff/api_contract_diff.py \
  old_spec.yaml \
  new_spec.yaml \
  --format markdown
```

### Supported Formats

- OpenAPI v3.0 / v3.1 (JSON/YAML)
- Swagger v2.0 (JSON/YAML)

### Detected Breaking Changes

- Removed endpoints (e.g. `GET /users` is gone).
- Removed HTTP methods on an endpoint (e.g. `POST /users` is gone).
- Removed request parameters.
- Changed request parameters from optional to required.
- Changed request parameter type.
- Removed fields in response schemas.
- Changed response schema field type.
- Changed field from required to optional in response body.
- Added required fields to request body.
- Removed successful status codes (e.g., successful status 200 removed).
- Added enum values to response field schemas (can break strict deserializers).
- Removed enum values from request parameters.

## Requirements

- `pyyaml`

## Quality

Quality: pylint 10.00/10 · 100% coverage · 1 dependencies
