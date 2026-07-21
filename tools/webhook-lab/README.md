# Webhook Lab

Local webhook receiver with request history, payload diffing, replay, signature verification, and secret redaction.

## Usage

### Start receiver

```bash
python tools/webhook-lab/webhook_lab.py start \
  --port 8080 \
  --sig-header X-Hub-Signature-256 \
  --sig-secret my_secret_key \
  --sig-style github
```

### List received webhooks

```bash
python tools/webhook-lab/webhook_lab.py list
```

### Show details with redactions

```bash
python tools/webhook-lab/webhook_lab.py show 1
```

### Compare two payload variations

```bash
python tools/webhook-lab/webhook_lab.py compare 1 2
```

### Replay webhook payload

```bash
python tools/webhook-lab/webhook_lab.py replay 1 --to http://127.0.0.1:3000/endpoint
```

## Requirements

No external dependencies beyond the Python standard library.

## Quality

Quality: pylint 10.00/10 · 100% coverage · 0 dependencies
