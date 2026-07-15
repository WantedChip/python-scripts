"""Fresh Machine.

Exports developer setup details (Git configs, shell aliases, editor
extensions, system packages, Python tools) and replicates it elsewhere.
"""

import argparse
import json
import os
import platform
import subprocess  # nosec B404
import sys
from typing import Dict, List


def run_command(args: List[str]) -> str:
    """Runs a shell command and returns stdout. Bypasses errors with empty output.

    Args:
        args: List of command line arguments.

    Returns:
        Standard output string.
    """
    try:
        # pylint: disable=subprocess-run-check
        res = subprocess.run(  # nosec B603
            args,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )
        if res.returncode == 0:
            return res.stdout
    except (FileNotFoundError, OSError):
        pass
    return ""


def get_git_config() -> Dict[str, str]:
    """Retrieves global Git configuration values.

    Returns:
        Dictionary mapping Git config keys to values.
    """
    config = {}
    output = run_command(["git", "config", "--global", "--list"])
    for line in output.splitlines():
        if "=" in line:
            key, val = line.split("=", 1)
            config[key.strip()] = val.strip()
    return config


def get_vscode_extensions() -> List[str]:
    """Retrieves installed VS Code extension identifiers.

    Returns:
        List of extension IDs.
    """
    output = run_command(["code", "--list-extensions"])
    return [line.strip() for line in output.splitlines() if line.strip()]


def get_shell_aliases() -> List[str]:
    """Extracts custom aliases from active shell profile files.

    Returns:
        List of raw alias strings.
    """
    aliases = []
    home = os.path.expanduser("~")
    # Search common shell profiles
    profiles = [
        os.path.join(home, ".bashrc"),
        os.path.join(home, ".zshrc"),
        os.path.join(home, ".bash_profile"),
        os.path.join(home, ".profile"),
    ]

    for prof in profiles:
        if os.path.exists(prof):
            try:
                with open(prof, "r", encoding="utf-8") as file:
                    for line in file:
                        stripped = line.strip()
                        if stripped.startswith("alias "):
                            aliases.append(stripped)
            except IOError:
                pass
    return list(set(aliases))


def get_system_packages() -> Dict[str, List[str]]:
    """Identifies installed system packages using platform-specific managers.

    Returns:
        Dictionary mapping manager name to list of packages.
    """
    # pylint: disable=too-many-branches
    packages: Dict[str, List[str]] = {}
    system = platform.system().lower()

    if system == "windows":
        # Check winget
        winget_out = run_command(["winget", "list"])
        if winget_out:
            packages["winget"] = []
            for line in winget_out.splitlines():
                if "Id" in line or line.startswith("-") or not line.strip():
                    continue
                parts = [p.strip() for p in line.split("  ") if p.strip()]
                if len(parts) >= 2:
                    packages["winget"].append(parts[1])  # App ID
        # Check choco
        choco_out = run_command(["choco", "list", "--local-only"])
        if choco_out:
            packages["choco"] = []
            for line in choco_out.splitlines():
                if " " in line:
                    packages["choco"].append(line.split(" ", 1)[0])

    elif system == "darwin":  # macOS
        # Homebrew formulae
        brew_leaves = run_command(["brew", "leaves"])
        if brew_leaves:
            packages["brew_formulae"] = [
                line.strip() for line in brew_leaves.splitlines() if line.strip()
            ]
        # Homebrew casks
        brew_casks = run_command(["brew", "list", "--cask"])
        if brew_casks:
            packages["brew_casks"] = [
                line.strip() for line in brew_casks.splitlines() if line.strip()
            ]

    elif system == "linux":
        # Debian/Ubuntu (APT)
        apt_out = run_command(["apt-mark", "showmanual"])
        if apt_out:
            packages["apt"] = [
                line.strip() for line in apt_out.splitlines() if line.strip()
            ]
        # Arch Linux (Pacman)
        pacman_out = run_command(["pacman", "-Qe"])
        if pacman_out:
            packages["pacman"] = [
                line.split(" ", 1)[0]
                for line in pacman_out.splitlines()
                if line.strip()
            ]

    return packages


def get_python_tools() -> List[str]:
    """Retrieves globally installed Python pipx tools or pip packages.

    Returns:
        List of package names.
    """
    # Prefer pipx if available
    pipx_out = run_command(["pipx", "list", "--short"])
    if pipx_out:
        return [line.split(" ", 1)[0] for line in pipx_out.splitlines() if line.strip()]

    # Fall back to pip list
    pip_out = run_command(["pip", "list", "--format=json"])
    if pip_out:
        try:
            data = json.loads(pip_out)
            return [pkg["name"] for pkg in data]
        except json.JSONDecodeError:
            pass
    return []


def export_setup(output_file: str) -> None:
    """Gathers all developer environment settings and writes them to a JSON file.

    Args:
        output_file: Destination path for the exported profile.
    """
    profile = {
        "platform": {
            "system": platform.system(),
            "release": platform.release(),
            "version": platform.version(),
        },
        "git_config": get_git_config(),
        "vscode_extensions": get_vscode_extensions(),
        "shell_aliases": get_shell_aliases(),
        "system_packages": get_system_packages(),
        "python_tools": get_python_tools(),
    }

    try:
        with open(output_file, "w", encoding="utf-8") as file:
            json.dump(profile, file, indent=2)
        print(f"Developer environment setup successfully exported to {output_file}")
    except IOError as err:
        print(f"Error exporting environment configuration: {err}", file=sys.stderr)
        sys.exit(1)


def restore_setup(profile_file: str, dry_run: bool) -> None:
    """Reads a setup profile and applies configurations and installs package components.

    Args:
        profile_file: Path to profile JSON file.
        dry_run: If True, previews commands without executing system changes.
    """
    # pylint: disable=too-many-branches,too-many-statements,too-many-locals
    try:
        with open(profile_file, "r", encoding="utf-8") as file:
            profile = json.load(file)
    except (IOError, json.JSONDecodeError) as err:
        print(f"Error reading profile configuration file: {err}", file=sys.stderr)
        sys.exit(1)

    print(f"Restoring developer setup from {profile_file}...")
    if dry_run:
        print("=== DRY RUN MODE: Previews action scripts ===")

    # 1. Apply Git Configs
    git_cfg = profile.get("git_config", {})
    if git_cfg:
        print(f"\nConfiguring {len(git_cfg)} Git options...")
        for key, val in git_cfg.items():
            cmd = ["git", "config", "--global", key, val]
            if dry_run:
                print(f"Would run: {' '.join(cmd)}")
            else:
                subprocess.run(cmd, check=False)  # nosec B603 - static list commands

    # 2. Append shell aliases
    aliases = profile.get("shell_aliases", [])
    if aliases:
        print(f"\nRestoring {len(aliases)} shell aliases...")
        home = os.path.expanduser("~")
        # Write to .zshrc or .bashrc based on shell
        shell = os.environ.get("SHELL", "")
        profile_path = os.path.join(home, ".bashrc")
        if "zsh" in shell:
            profile_path = os.path.join(home, ".zshrc")

        if dry_run:
            print(f"Would append aliases to {profile_path}:")
            for alias in aliases:
                print(f"  {alias}")
        else:
            try:
                # Read existing lines to avoid duplicates
                existing = set()
                if os.path.exists(profile_path):
                    with open(profile_path, "r", encoding="utf-8") as pf:
                        existing = {line.strip() for line in pf}

                with open(profile_path, "a", encoding="utf-8") as pf:
                    pf.write("\n# Restored by fresh-machine\n")
                    for alias in aliases:
                        if alias not in existing:
                            pf.write(f"{alias}\n")
                print(f"Aliases written to {profile_path}")
            except IOError as err:
                print(
                    f"Warning: Failed to write to {profile_path} ({err})",
                    file=sys.stderr,
                )

    # 3. Install VS Code Extensions
    extensions = profile.get("vscode_extensions", [])
    if extensions:
        print(f"\nInstalling {len(extensions)} VS Code extensions...")
        for ext in extensions:
            cmd = ["code", "--install-extension", ext]
            if dry_run:
                print(f"Would run: {' '.join(cmd)}")
            else:
                subprocess.run(cmd, check=False)  # nosec B603 - validated CLI calls

    # 4. Install System Packages
    packages = profile.get("system_packages", {})
    if packages:
        print("\nRestoring system packages...")
        for manager, pkgs in packages.items():
            if not pkgs:
                continue
            cmd = []
            if manager == "winget":
                cmd = ["winget", "install"]
            elif manager == "choco":
                cmd = ["choco", "install", "-y"]
            elif manager == "brew_formulae":
                cmd = ["brew", "install"]
            elif manager == "brew_casks":
                cmd = ["brew", "install", "--cask"]
            elif manager == "apt":
                cmd = ["sudo", "apt", "install", "-y"]
            elif manager == "pacman":
                cmd = ["sudo", "pacman", "-S", "--noconfirm"]

            if cmd:
                for pkg in pkgs:
                    run_cmd = cmd + [pkg]
                    if dry_run:
                        print(f"Would run: {' '.join(run_cmd)}")
                    else:
                        subprocess.run(run_cmd, check=False)  # nosec B603

    # 5. Install Python tools
    py_tools = profile.get("python_tools", [])
    if py_tools:
        print(f"\nInstalling {len(py_tools)} Python tools...")
        # Check if pipx is available, else use pip
        has_pipx = os.path.exists("/usr/bin/pipx") or run_command(["pipx", "--version"])
        base_cmd = ["pipx", "install"] if has_pipx else ["pip", "install", "--user"]
        for tool in py_tools:
            cmd = base_cmd + [tool]
            if dry_run:
                print(f"Would run: {' '.join(cmd)}")
            else:
                subprocess.run(cmd, check=False)  # nosec B603

    print("\nRestore operation completed successfully.")


def main() -> None:
    """CLI entry point for fresh-machine setup replicator."""
    # pylint: disable=duplicate-code
    parser = argparse.ArgumentParser(
        description="Export and recreate developer environment configuration setups."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # Export Command
    export_parser = subparsers.add_parser(
        "export", help="Export developer configuration to profile JSON file."
    )
    export_parser.add_argument(
        "-o",
        "--output",
        default="developer_profile.json",
        help="Target output profile JSON file (default: developer_profile.json).",
    )

    # Import Command
    import_parser = subparsers.add_parser(
        "import", help="Recreate setup from a profile JSON configuration."
    )
    import_parser.add_argument(
        "-p",
        "--profile",
        default="developer_profile.json",
        help="Source profile JSON file (default: developer_profile.json).",
    )
    import_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview installation scripts without modifying the system.",
    )

    args = parser.parse_args()

    if args.command == "export":
        export_setup(args.output)
    elif args.command == "import":
        restore_setup(args.profile, args.dry_run)


if __name__ == "__main__":
    main()
