# Firewall Rule Generator

Generates `iptables` or `ufw` shell script commands from a simple YAML or JSON firewall rule specification document.

## Rule Schema Example (YAML / JSON)

```yaml
rules:
  - action: allow
    direction: in
    protocol: tcp
    port: 80
    source: 192.168.1.0/24
    comment: "Allow HTTP traffic from local subnet"

  - action: deny
    direction: in
    protocol: tcp
    port: 22
    source: any
    comment: "Block SSH"
```

## Features

- **Multi-Target Support**: Generates scripts for `iptables` and `ufw`.
- **Validation**: Validates actions (`allow`/`deny`), directions (`in`/`out` or `input`/`output`), protocols (`tcp`/`udp`/`any`), ports, and IP/CIDR syntax.
- **YAML & JSON Parsing**: Supports both input file formats.

## Usage

```bash
# Generate iptables script from YAML rules
python main.py rules.yaml --target iptables --output firewall.sh

# Generate ufw script from JSON rules
python main.py rules.json --target ufw
```

## Running Tests

```bash
python -m unittest discover -s tests
```
