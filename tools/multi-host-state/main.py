"""Multi-Host State Clusterer & Summarizer.

Executes diagnostic commands across multiple hosts via SSH or parses host
output files, normalizes outputs to strip transient noise, and clusters hosts
with identical states.
"""

# pylint: disable=too-many-branches,too-many-statements
# pylint: disable=too-many-locals,too-many-arguments,too-many-positional-arguments
# pylint: disable=too-many-instance-attributes,too-few-public-methods

import argparse
import hashlib
import json
import os
import re
import subprocess  # nosec B404
import sys

# no-name-in-module: astroid cannot introspect concurrent.futures on some
# interpreter versions (py3.14); the import itself is valid on all of them.
from concurrent.futures import (  # pylint: disable=no-name-in-module
    ThreadPoolExecutor,
    as_completed,
)
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


def normalize_output(
    text: str,
    ignore_patterns: Optional[List[str]] = None,
    normalize_whitespace: bool = True,
    strip_timestamps: bool = True,
    strip_ips: bool = True,
) -> str:
    """Normalize raw diagnostic output by stripping volatile or host data.

    Args:
        text: Raw output string.
        ignore_patterns: Custom regex patterns to replace with placeholders.
        normalize_whitespace: Whether to collapse dynamic whitespace.
        strip_timestamps: Whether to replace common timestamp patterns.
        strip_ips: Whether to replace IP addresses with placeholder.

    Returns:
        Normalized string ready for fingerprinting.
    """
    normalized = text

    if strip_timestamps:
        # ISO timestamps, syslog dates, uptime timestamps
        iso_pat = (
            r"\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}"
            r"(?:\.\d+)?(?:Z|[+-]\d{2}:?\d{2})?"
        )
        normalized = re.sub(iso_pat, "[TIMESTAMP]", normalized)
        syslog_pat = (
            r"(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)"
            r"\s+\d+\s+\d{2}:\d{2}:\d{2}"
        )
        normalized = re.sub(syslog_pat, "[TIMESTAMP]", normalized)
        normalized = re.sub(r"up\s+\d+\s+days?,\s+\d+:\d+", "up [UPTIME]", normalized)

    if strip_ips:
        ip_pat = r"\b(?:\d{1,3}\.){3}\d{1,3}\b"
        normalized = re.sub(ip_pat, "[IP_ADDR]", normalized)

    if ignore_patterns:
        for pat in ignore_patterns:
            try:
                normalized = re.sub(pat, "[FILTERED]", normalized)
            except re.error:
                pass

    if normalize_whitespace:
        # Normalize line endings and trim lines
        lines = [line.strip() for line in normalized.splitlines()]
        normalized = "\n".join(lines).strip()

    return normalized


def compute_fingerprint(text: str) -> str:
    """Generate SHA256 hex digest for normalized text."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:12]


def load_outputs_from_directory(dir_path: Path) -> Dict[str, str]:
    """Read host output files from a directory.

    Filenames are assumed to be hostnames (e.g. host1.txt -> host1).
    """
    results = {}
    if not dir_path.exists() or not dir_path.is_dir():
        raise ValueError(f"Directory non-existent or invalid: {dir_path}")

    for file in sorted(dir_path.glob("*")):
        if file.is_file() and not file.name.startswith("."):
            hostname = file.stem
            try:
                text = file.read_text(encoding="utf-8", errors="replace")
                results[hostname] = text
            except OSError as e:
                results[hostname] = f"ERROR: Failed to read file: {e}"
    return results


def run_ssh_host_command(
    host: str,
    command: str,
    user: Optional[str] = None,
    key_file: Optional[str] = None,
    timeout: int = 10,
) -> Tuple[str, str]:
    """Execute SSH command on a single target host using system ssh command.

    Returns tuple (hostname, stdout_or_error).
    """
    target = f"{user}@{host}" if user else host
    cmd = ["ssh", "-o", "BatchMode=yes", "-o", f"ConnectTimeout={timeout}"]
    if key_file:
        cmd.extend(["-i", key_file])
    cmd.extend([target, command])

    try:
        res = subprocess.run(  # nosec B603 B607
            cmd, capture_output=True, text=True, timeout=timeout + 5, check=False
        )
        if res.returncode == 0:
            return host, res.stdout
        err_msg = res.stderr.strip()
        return host, f"SSH ERROR (code {res.returncode}): {err_msg}"
    except subprocess.TimeoutExpired:
        return host, f"SSH ERROR: Connection timed out after {timeout}s"
    except OSError as e:
        return host, f"SSH ERROR: {e}"


def fetch_ssh_outputs(
    hosts: List[str],
    command: str,
    user: Optional[str] = None,
    key_file: Optional[str] = None,
    max_workers: int = 10,
    timeout: int = 10,
) -> Dict[str, str]:
    """Run SSH command in parallel across multiple hosts."""
    results = {}
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(
                run_ssh_host_command, host, command, user, key_file, timeout
            ): host
            for host in hosts
        }
        for future in as_completed(futures):
            host, output = future.result()
            results[host] = output
    return results


def cluster_host_outputs(
    host_outputs: Dict[str, str],
    ignore_patterns: Optional[List[str]] = None,
    normalize_ws: bool = True,
) -> List[Dict[str, Any]]:
    """Group hosts by identical normalized outputs/fingerprints."""
    clusters_map: Dict[str, Dict[str, Any]] = {}

    for host, raw_out in host_outputs.items():
        norm_out = normalize_output(
            raw_out,
            ignore_patterns=ignore_patterns,
            normalize_whitespace=normalize_ws,
        )
        fp = compute_fingerprint(norm_out)

        if fp not in clusters_map:
            clusters_map[fp] = {
                "fingerprint": fp,
                "hosts": [],
                "normalized_sample": norm_out,
                "raw_sample": raw_out,
                "count": 0,
            }

        clusters_map[fp]["hosts"].append(host)
        clusters_map[fp]["count"] += 1

    # Sort clusters by host count descending
    sorted_clusters = sorted(
        clusters_map.values(), key=lambda c: int(c["count"]), reverse=True
    )
    return sorted_clusters


def format_cluster_summary(
    clusters: List[Dict[str, Any]], verbose: bool = False
) -> str:
    """Format clusters into human readable report."""
    total_hosts = sum(int(c["count"]) for c in clusters)
    lines = [
        "=" * 60,
        " MULTI-HOST STATE CLUSTER REPORT",
        f" Total Hosts: {total_hosts} | Unique Clusters: {len(clusters)}",
        "=" * 60,
        "",
    ]

    for idx, cluster in enumerate(clusters, 1):
        fp = cluster["fingerprint"]
        count = cluster["count"]
        hosts = ", ".join(sorted(cluster["hosts"]))
        lines.append(f"Cluster #{idx} [Fingerprint: {fp}] - {count} host(s)")
        lines.append(f"  Hosts: {hosts}")
        lines.append("  Sample Output:")
        sample = cluster["normalized_sample"]
        sample_lines = sample.splitlines()
        display_lines = sample_lines[:8] if not verbose else sample_lines
        for s in display_lines:
            lines.append(f"    | {s}")
        if len(sample_lines) > 8 and not verbose:
            rem = len(sample_lines) - 8
            lines.append(f"    | ... ({rem} more lines omitted)")
        lines.append("-" * 60)

    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    """Build CLI parser."""
    desc = "Summarize multi-host state into unique clusters."
    parser = argparse.ArgumentParser(description=desc)
    parser.add_argument(
        "--dir", type=str, help="Directory containing host output files."
    )
    parser.add_argument(
        "--hosts", type=str, help="Comma-separated hostnames or path to file."
    )
    parser.add_argument("--command", type=str, help="SSH command to run across hosts.")
    parser.add_argument("--user", type=str, help="SSH username.")
    parser.add_argument("--key", type=str, help="SSH private key path.")
    parser.add_argument(
        "--ignore-pattern",
        action="append",
        help="Custom regex pattern to ignore during normalization.",
    )
    parser.add_argument(
        "--json", action="store_true", help="Output results in JSON format."
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Show full sample output for clusters.",
    )
    parser.add_argument("--output", type=str, help="Save summary report to file.")
    return parser


def main(args: Optional[List[str]] = None) -> int:
    """CLI entrypoint."""
    parser = build_parser()
    parsed = parser.parse_args(args)

    host_outputs: Dict[str, str] = {}

    if parsed.dir:
        dir_path = Path(parsed.dir)
        host_outputs = load_outputs_from_directory(dir_path)
    elif parsed.hosts and parsed.command:
        if os.path.exists(parsed.hosts):
            hosts_list = [
                line.strip()
                for line in Path(parsed.hosts).read_text(encoding="utf-8").splitlines()
                if line.strip() and not line.startswith("#")
            ]
        else:
            hosts_list = [h.strip() for h in parsed.hosts.split(",") if h.strip()]

        print(f"Executing '{parsed.command}' across {len(hosts_list)} hosts...")
        host_outputs = fetch_ssh_outputs(
            hosts_list, parsed.command, user=parsed.user, key_file=parsed.key
        )
    else:
        err_msg = "Either --dir OR both (--hosts and --command) must be provided."
        parser.error(err_msg)

    clusters = cluster_host_outputs(host_outputs, ignore_patterns=parsed.ignore_pattern)

    if parsed.json:
        report_data = {
            "total_hosts": len(host_outputs),
            "unique_clusters": len(clusters),
            "clusters": clusters,
        }
        output_str = json.dumps(report_data, indent=2)
    else:
        output_str = format_cluster_summary(clusters, verbose=parsed.verbose)

    if parsed.output:
        Path(parsed.output).write_text(output_str, encoding="utf-8")
        print(f"Report written to {parsed.output}")
    else:
        print(output_str)

    return 0


if __name__ == "__main__":
    sys.exit(main())
