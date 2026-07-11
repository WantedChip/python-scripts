"""Command History Analyzer.

A utility to scan local shell history logs (Bash, Zsh, PowerShell),
identify most frequent commands, and auto-suggest shell aliases.
"""

import argparse
import collections
import json
import logging
import os
import sys
from pathlib import Path
from typing import Generator, List, Tuple

# pylint: disable=duplicate-code

logger = logging.getLogger("history_analyzer")


# Predefined common short-name mappings for suggestion generator
COMMON_ALIASES = {
    "git checkout": "gco",
    "git commit": "gc",
    "git status": "gst",
    "git push": "gp",
    "git pull": "gpl",
    "git diff": "gd",
    "docker compose": "dc",
    "python -m venv": "pmv",
    "kubectl get pods": "kgp",
}


def setup_logging(verbose: bool) -> None:
    """Configure logging format and level."""
    level = logging.DEBUG if verbose else logging.INFO
    handler = logging.StreamHandler(sys.stdout)
    formatter = logging.Formatter(
        "%(asctime)s - %(levelname)s - %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
    )
    handler.setFormatter(formatter)
    logger.setLevel(level)
    logger.addHandler(handler)
    logging.basicConfig(level=logging.WARNING, handlers=[handler])


def get_default_history_path(shell: str) -> Path:
    """Resolve standard local file path for shell history logs based on OS.

    Args:
        shell: Target shell name ('bash', 'zsh', 'powershell').

    Returns:
        Path to history log file.
    """
    home_env = os.environ.get("HOME") or os.environ.get("USERPROFILE")
    home = Path(home_env) if home_env else Path.home()
    if shell == "bash":
        return home / ".bash_history"
    if shell == "zsh":
        # Check ZDOTDIR env var fallback
        zdotdir = os.environ.get("ZDOTDIR")
        if zdotdir:
            return Path(zdotdir) / ".zsh_history"
        return home / ".zsh_history"
    if shell == "powershell":
        if os.name == "nt":
            appdata = os.environ.get("APPDATA")
            if appdata:
                return (
                    Path(appdata)
                    / "Microsoft"
                    / "Windows"
                    / "PowerShell"
                    / "PSReadLine"
                    / "ConsoleHost_history.txt"
                )
        # Linux/macOS powershell history path fallback
        return home / ".config" / "powershell" / "ConsoleHost_history.txt"

    raise ValueError(f"Unsupported shell: {shell}")


def parse_history_lines(lines: List[str], shell: str) -> Generator[str, None, None]:
    """Parse raw history file lines, stripping dates and formats.

    Args:
        lines: List of raw strings from history file.
        shell: shell type format to clean.

    Yields:
        Parsed clean command string.
    """
    # Detect if any line starts with colon (Zsh extended format)
    has_extended = any(line.strip().startswith(":") for line in lines)

    for line in lines:
        cleaned = line.strip()
        if not cleaned:
            continue

        if shell == "zsh":
            # Zsh extended format matches: ': 1690000000:0;cmd arguments'
            if cleaned.startswith(":"):
                parts = cleaned.split(";", 1)
                if len(parts) > 1:
                    cleaned = parts[1].strip()
                else:
                    continue
            elif has_extended:
                # Skip simple line if file is in extended format
                continue
        elif shell == "bash":
            # Bash extended timestamp lines start with '#' and epoch time
            if cleaned.startswith("#") and cleaned[1:].strip().isdigit():
                continue

        if cleaned:
            yield cleaned


def clean_base_command(cmd_str: str) -> str:
    """Extract standard base command and direct sub-commands.

    Args:
        cmd_str: full command string (e.g. 'git commit -m "message"')

    Returns:
        String representing base action.
    """
    tokens = cmd_str.split()
    if not tokens:
        return ""

    base = tokens[0]

    # Include first sub-command argument for common complex tools
    if (
        base in ["git", "docker", "kubectl", "npm", "pip", "python", "cargo"]
        and len(tokens) > 1
    ):
        # Avoid flags as sub-commands (e.g. 'python -m' or 'git -C')
        if not tokens[1].startswith("-"):
            return f"{base} {tokens[1]}"

    return base


def suggest_alias(cmd: str) -> str:
    """Generate potential shorthand command alias.

    Args:
        cmd: transaction command string.

    Returns:
        Shorthand alias suggestion string.
    """
    # 1. Check known defaults mapping
    if cmd in COMMON_ALIASES:
        return COMMON_ALIASES[cmd]

    # 2. Extract initials heuristic for custom long commands
    tokens = cmd.split()
    if len(tokens) > 1:
        # e.g. 'docker compose' -> 'dc', 'git checkout' -> 'gco'
        alias_candidate = "".join(token[0] for token in tokens if token.isalnum())
        if alias_candidate and len(alias_candidate) > 1:
            return alias_candidate.lower()

    # Fallback to suffix shorthand
    return cmd[:3] if len(cmd) > 3 else cmd


def analyze_history(
    history_file: Path, shell: str, top_n: int
) -> Tuple[List[Tuple[str, int]], List[Tuple[str, int]], List[Tuple[str, int, str]]]:
    """Audit local shell log and compile command usage summaries.

    Args:
        history_file: Path to history log file.
        shell: target shell category.
        top_n: limit for report listings.

    Returns:
        Tuple containing:
        - List of top base command usage frequencies.
        - List of top full command usage frequencies.
        - List of alias suggestions: (long_command, occurrences, alias_shorthand).
    """
    try:
        # Use latin-1/utf-8 with replace to handle non-unicode sequences safely
        with open(history_file, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
    except Exception as err:  # pylint: disable=broad-exception-caught
        logger.error("Failed to read history file %s: %s", history_file.name, err)
        return [], [], []

    # Clean commands
    commands = list(parse_history_lines(lines, shell))
    if not commands:
        return [], [], []

    # Counts
    full_counter = collections.Counter(commands)
    base_counter = collections.Counter(clean_base_command(cmd) for cmd in commands)

    top_full = full_counter.most_common(top_n)
    top_base = base_counter.most_common(top_n)

    # Alias Suggestions
    # Filter for commands that are long enough and repeated frequently
    suggestions = []
    # Identify unique long commands with high repetitions
    for cmd, count in full_counter.most_common(50):
        # Recommend aliases for commands with spaces (multi-word) or
        # long strings (> 7 chars)

        if count >= 3 and (len(cmd) > 7 or " " in cmd):
            alias = suggest_alias(cmd)
            # Prevent suggesting the command name itself
            if alias != cmd:
                suggestions.append((cmd, count, alias))

    # Return top N suggestions
    return top_base, top_full, suggestions[:top_n]


def print_terminal_summary(
    shell: str,
    top_base: List[Tuple[str, int]],
    top_full: List[Tuple[str, int]],
    suggestions: List[Tuple[str, int, str]],
) -> None:
    """Print history report tables in clean console layouts."""
    sys.stdout.write(f"\n=== Shell History Analysis Report ({shell.upper()}) ===\n")

    sys.stdout.write("\nTop Base/Tool Commands:\n")
    for cmd, count in top_base:
        sys.stdout.write(f"  - {cmd:<25}: {count} times\n")

    sys.stdout.write("\nTop Exact Full Commands:\n")
    for cmd, count in top_full:
        # Truncate command display if excessively long
        display_cmd = cmd if len(cmd) <= 45 else cmd[:42] + "..."
        sys.stdout.write(f"  - {display_cmd:<45}: {count} times\n")

    sys.stdout.write("\nSuggested Command Aliases:\n")
    if not suggestions:
        sys.stdout.write(
            "  No command repetitions met alias recommendation criteria.\n"
        )
    for cmd, count, alias in suggestions:
        display_cmd = cmd if len(cmd) <= 30 else cmd[:27] + "..."
        sys.stdout.write(
            f"  - Alias '{alias}' -> '{display_cmd}' (run {count} times)\n"
        )
    sys.stdout.write("\n=======================================================\n")


def main() -> None:
    """CLI execution entry point."""
    parser = argparse.ArgumentParser(
        description=(
            "Command History Analyzer — audit shell usage stats "
            "and identify alias candidates."
        )
    )

    parser.add_argument(
        "-s",
        "--shell",
        choices=["bash", "zsh", "powershell"],
        help="Target shell history format (guesses current system shell by default).",
    )
    parser.add_argument(
        "-i", "--input", type=Path, help="Explicit path to shell history file."
    )
    parser.add_argument(
        "-n",
        "--count",
        type=int,
        default=10,
        help="Number of records to display (default: 10).",
    )
    parser.add_argument("-o", "--output", type=Path, help="Output file path (JSON).")
    parser.add_argument(
        "-v", "--verbose", action="store_true", help="Enable verbose debug logging."
    )

    args = parser.parse_args()
    setup_logging(args.verbose)

    # 1. Determine shell and file path
    shell = args.shell
    if not shell:
        # Heuristically detect system shell from environment
        shell_env = os.environ.get("SHELL", "").lower()
        if "zsh" in shell_env:
            shell = "zsh"
        elif "bash" in shell_env:
            shell = "bash"
        elif os.name == "nt":
            shell = "powershell"
        else:
            shell = "bash"  # Default fallback

    history_path = args.input
    if not history_path:
        try:
            history_path = get_default_history_path(shell)
        except ValueError as err:
            logger.error(err)
            sys.exit(1)

    if not history_path.exists():
        logger.error(
            "Resolved history file not found: %s. Use --input to specify direct path.",
            history_path.as_posix(),
        )
        sys.exit(1)

    logger.info("Analyzing %s history log: %s", shell, history_path.as_posix())

    # 2. Run analysis audit
    top_base, top_full, suggestions = analyze_history(history_path, shell, args.count)

    if not top_base:
        logger.warning("No commands found in the history file.")
        sys.exit(0)

    # 3. Output results
    if args.output:
        try:
            with open(args.output, "w", encoding="utf-8") as f:
                json.dump(
                    {
                        "shell": shell,
                        "top_base_commands": [
                            {"command": cmd, "count": cnt} for cmd, cnt in top_base
                        ],
                        "top_full_commands": [
                            {"command": cmd, "count": cnt} for cmd, cnt in top_full
                        ],
                        "suggested_aliases": [
                            {"command": cmd, "count": cnt, "suggested_alias": alias}
                            for cmd, cnt, alias in suggestions
                        ],
                    },
                    f,
                    indent=2,
                )
            logger.info("History audit saved to JSON path: %s", args.output.as_posix())
        except Exception as err:  # pylint: disable=broad-exception-caught
            logger.error("Failed to save JSON output: %s", err)
            sys.exit(1)
    else:
        print_terminal_summary(shell, top_base, top_full, suggestions)


if __name__ == "__main__":
    main()
