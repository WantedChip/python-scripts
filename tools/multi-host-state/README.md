# Multi-Host State Clusterer

Analyze diagnostic outputs across multiple machines and group them into unique state clusters based on normalized fingerprints.

## Features
- **Directory Mode**: Read pre-collected host output files from a directory.
- **SSH Mode**: Concurrently execute a diagnostic command over SSH across multiple hosts.
- **Output Normalization**: Automatically strip dynamic timestamps, IP addresses, uptime counters, and custom regex patterns.
- **Clustering**: Group hosts with identical state output into single clusters with fingerprints.
- **Export Options**: Output human-readable summary reports or JSON data.

## Usage

### Analyze output files from a directory
```bash
python main.py --dir /path/to/host_outputs/
```

### Run SSH command across hosts
```bash
python main.py --hosts host1,host2,host3 --command "uptime" --user admin
```

### JSON export with custom filter patterns
```bash
python main.py --dir /path/to/outputs --ignore-pattern "PID:\s*\d+" --json --output cluster_report.json
```
