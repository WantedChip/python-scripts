# Process Port Inspector

Show which process owns each port and optionally terminate it safely or forcefully.

## Usage

```bash
python port_inspector.py [options]
```

### Examples

```bash
# List all active connections and ports
python port_inspector.py

# List only UDP ports
python port_inspector.py --proto udp

# Inspect a specific port (e.g. port 8080)
python port_inspector.py -p 8080

# Terminate the process owning port 8080 (asks for confirmation)
python port_inspector.py -p 8080 --kill

# Forcefully terminate the process owning port 8080 (no prompt)
python port_inspector.py -p 8080 --kill --force

# Output connection and owner details as JSON
python port_inspector.py -j
```

## Requirements

Requires `psutil` library. Install it using the following:

```bash
pip install -r requirements.txt
```

## Notes

* To see process information (like name, path, owner) for ports owned by system services or other users, you **must run the script as Administrator / Root**. If run without administrative privileges, some columns might display "Access Denied" for processes owned by other users or the operating system.
* Termination logic sends a soft `SIGTERM` / `.terminate()` signal first to let the process clean up. If that fails or if `--force` is set, it sends a forceful `SIGKILL` / `.kill()`.

Quality: pylint 10.00/10 · 91% coverage · 1 dependencies
