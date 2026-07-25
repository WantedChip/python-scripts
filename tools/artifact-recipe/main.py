"""Artifact Recipe: Provenance sidecar & explanation CLI.

Records build provenance for generated files into `.recipe.json` sidecar files,
capturing input files, hashes, commands, env vars, and system environment.
Provides an `explain` command to check artifact staleness and input file changes.
"""

# pylint: disable=too-many-branches,too-many-statements
# pylint: disable=too-many-locals,too-many-arguments,too-many-positional-arguments

import argparse
import hashlib
import json
import os
import platform
import subprocess  # nosec B404
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

ARGPARSE_DESC = "Artifact Recipe: Provenance sidecar & explanation tool."


def compute_file_hash(file_path: Path) -> str:
    """Compute SHA-256 hash of a file."""
    if not file_path.exists() or not file_path.is_file():
        return ""
    hasher = hashlib.sha256()
    with file_path.open("rb") as f:
        while chunk := f.read(65536):
            hasher.update(chunk)
    return hasher.hexdigest()


def collect_env_vars(var_names: Optional[List[str]]) -> Dict[str, str]:
    """Collect specified environment variables."""
    if not var_names:
        return {}
    return {var: os.environ.get(var, "") for var in var_names}


def create_recipe(
    artifact_path: Path,
    command: str,
    input_paths: List[Path],
    env_vars: Optional[List[str]] = None,
    cwd: Optional[Path] = None,
) -> Dict[str, Any]:
    """Create provenance recipe dictionary for an artifact."""
    cwd_path = (cwd or Path.cwd()).resolve()

    input_records = []
    for inp in input_paths:
        resolved = inp.resolve()
        m_val = resolved.stat().st_mtime if resolved.exists() else 0
        s_val = resolved.stat().st_size if resolved.exists() else 0
        input_records.append(
            {
                "path": str(resolved),
                "relative_path": os.path.relpath(resolved, cwd_path),
                "sha256": compute_file_hash(resolved),
                "mtime": m_val,
                "size_bytes": s_val,
            }
        )

    art_res = artifact_path.resolve()
    a_mtime = art_res.stat().st_mtime if art_res.exists() else 0
    a_size = art_res.stat().st_size if art_res.exists() else 0

    recipe = {
        "artifact": {
            "path": str(art_res),
            "relative_path": os.path.relpath(art_res, cwd_path),
            "sha256": compute_file_hash(art_res),
            "mtime": a_mtime,
            "size_bytes": a_size,
        },
        "provenance": {
            "command": command,
            "working_directory": str(cwd_path),
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "python_version": sys.version.split()[0],
            "platform": platform.platform(),
            "environment_variables": collect_env_vars(env_vars),
        },
        "inputs": input_records,
    }
    return recipe


def save_recipe(recipe: Dict[str, Any], recipe_file: Path) -> None:
    """Save recipe dictionary to sidecar JSON file."""
    recipe_file.write_text(json.dumps(recipe, indent=2), encoding="utf-8")


def load_recipe(recipe_file: Path) -> Dict[str, Any]:
    """Load recipe dictionary from sidecar JSON file."""
    data = json.loads(recipe_file.read_text(encoding="utf-8"))
    if isinstance(data, dict):
        return data
    return {}


def get_recipe_path_for_artifact(artifact_path: Path) -> Path:
    """Get standard sidecar recipe path for an artifact."""
    return artifact_path.parent / f"{artifact_path.name}.recipe.json"


def explain_artifact(recipe_file: Path) -> Dict[str, Any]:
    """Analyze artifact staleness and provenance from a recipe file."""
    recipe = load_recipe(recipe_file)
    artifact_meta = recipe["artifact"]
    provenance = recipe["provenance"]
    inputs_meta = recipe["inputs"]

    artifact_path = Path(artifact_meta["path"])
    status = "UP_TO_DATE"
    details = []

    # Check artifact existence and hash
    if not artifact_path.exists():
        status = "ARTIFACT_MISSING"
        details.append(f"Artifact file '{artifact_path}' no longer exists.")
    else:
        current_art_hash = compute_file_hash(artifact_path)
        if current_art_hash != artifact_meta["sha256"]:
            status = "ARTIFACT_MUTATED"
            rec_h = artifact_meta["sha256"][:8]
            cur_h = current_art_hash[:8]
            msg = (
                f"Artifact file was modified out-of-band "
                f"(recorded SHA256: {rec_h}, current: {cur_h})."
            )
            details.append(msg)

    # Check input files status
    changed_inputs = []
    missing_inputs = []

    for inp in inputs_meta:
        inp_path = Path(inp["path"])
        if not inp_path.exists():
            missing_inputs.append(inp["path"])
        else:
            curr_hash = compute_file_hash(inp_path)
            if curr_hash != inp["sha256"]:
                changed_inputs.append(inp["path"])

    if missing_inputs:
        status = "STALE_MISSING_INPUT"
        details.append(f"Input file(s) missing: {', '.join(missing_inputs)}")
    elif changed_inputs and status == "UP_TO_DATE":
        status = "STALE_INPUT_CHANGED"
        msg = (
            f"Input file(s) modified since generation: " f"{', '.join(changed_inputs)}"
        )
        details.append(msg)

    return {
        "recipe_file": str(recipe_file),
        "status": status,
        "artifact_path": artifact_meta["path"],
        "command": provenance["command"],
        "generated_at": provenance["timestamp_utc"],
        "working_directory": provenance["working_directory"],
        "details": details,
        "changed_inputs": changed_inputs,
        "missing_inputs": missing_inputs,
    }


def record_command(args: argparse.Namespace) -> int:
    """Execute record command."""
    artifact_path = Path(args.artifact).resolve()
    input_paths = [Path(p).resolve() for p in (args.inputs or [])]

    cmd = args.command
    if args.run:
        print(f"Executing command: {cmd}")
        res = subprocess.run(  # nosec B602 B603
            cmd, shell=True, cwd=args.cwd or os.getcwd(), check=False
        )
        if res.returncode != 0:
            err_msg = f"Error: Command failed with exit code {res.returncode}"
            print(err_msg, file=sys.stderr)
            return res.returncode

    recipe = create_recipe(
        artifact_path=artifact_path,
        command=cmd,
        input_paths=input_paths,
        env_vars=args.env_vars,
        cwd=Path(args.cwd) if args.cwd else None,
    )

    if args.output:
        sidecar_path = Path(args.output)
    else:
        sidecar_path = get_recipe_path_for_artifact(artifact_path)

    save_recipe(recipe, sidecar_path)
    print(f"Recorded provenance sidecar to: {sidecar_path}")
    return 0


def explain_command(args: argparse.Namespace) -> int:
    """Execute explain command."""
    target = Path(args.target).resolve()
    if target.suffix == ".json" and target.name.endswith(".recipe.json"):
        recipe_file = target
    else:
        recipe_file = get_recipe_path_for_artifact(target)

    if not recipe_file.exists():
        err = f"Error: Recipe sidecar '{recipe_file}' does not exist."
        print(err, file=sys.stderr)
        return 1

    res = explain_artifact(recipe_file)

    if args.format == "json":
        print(json.dumps(res, indent=2))
        return 0

    print("=== Artifact Provenance & Staleness Explanation ===")
    print(f"Artifact:    {res['artifact_path']}")
    print(f"Status:      [{res['status']}]")
    print(f"Command:     {res['command']}")
    print(f"Created At:  {res['generated_at']}")
    print(f"Work Dir:    {res['working_directory']}")

    if res["details"]:
        print("\nDetails:")
        for d in res["details"]:
            print(f"  - {d}")
    else:
        msg = (
            "\nArtifact is fully UP TO DATE and matches all recorded " + "input hashes."
        )
        print(msg)

    return 0


def verify_command(args: argparse.Namespace) -> int:
    """Execute verify command to check all sidecar recipes in a directory."""
    root_path = Path(args.path).resolve()
    recipe_files = list(root_path.rglob("*.recipe.json"))

    if not recipe_files:
        print("No .recipe.json sidecar files found.")
        return 0

    results = [explain_artifact(rf) for rf in recipe_files]

    if args.format == "json":
        print(json.dumps(results, indent=2))
        return 0

    print(f"=== Verifying {len(recipe_files)} Artifact Recipes ===")
    stale_count = 0
    for r in results:
        flag = "OK" if r["status"] == "UP_TO_DATE" else "STALE"
        if flag == "STALE":
            stale_count += 1
        print(f"[{flag}] {r['status']}: {r['artifact_path']}")

    ok_count = len(recipe_files) - stale_count
    msg = f"\nSummary: {ok_count} Up to date, {stale_count} Stale/Mutated."
    print(msg)
    if stale_count > 0:
        return 1
    return 0


def build_parser() -> argparse.ArgumentParser:
    """Build CLI parser."""
    parser = argparse.ArgumentParser(description=ARGPARSE_DESC)
    subparsers = parser.add_subparsers(dest="subcommand", required=True)

    # Subcommand: record
    rec_help = "Record artifact generation recipe sidecar"
    rec_parser = subparsers.add_parser("record", help=rec_help)
    rec_parser.add_argument(
        "--artifact", "-a", required=True, help="Target artifact file path"
    )
    rec_parser.add_argument(
        "--command",
        "-c",
        required=True,
        help="Command line used to create artifact",
    )
    rec_parser.add_argument("--inputs", "-i", nargs="*", help="Input dependency files")
    rec_parser.add_argument(
        "--env-vars", nargs="*", help="Environment variable names to record"
    )
    rec_parser.add_argument("--cwd", help="Working directory of execution")
    rec_parser.add_argument(
        "--run",
        action="store_true",
        help="Execute the command before recording",
    )
    rec_parser.add_argument("--output", "-o", help="Custom sidecar recipe file path")

    # Subcommand: explain
    exp_help = "Explain how artifact was created and verify staleness"
    exp_parser = subparsers.add_parser("explain", help=exp_help)
    exp_parser.add_argument(
        "target", help="Artifact file path or .recipe.json sidecar path"
    )
    exp_parser.add_argument(
        "--format",
        choices=["text", "json"],
        default="text",
        help="Output format",
    )

    # Subcommand: verify
    ver_help = "Verify all recipe sidecars in directory"
    ver_parser = subparsers.add_parser("verify", help=ver_help)
    ver_parser.add_argument(
        "path", nargs="?", default=".", help="Directory to search recipes in"
    )
    ver_parser.add_argument(
        "--format",
        choices=["text", "json"],
        default="text",
        help="Output format",
    )

    return parser


def main(args: Optional[List[str]] = None) -> int:
    """Main CLI entrypoint for artifact-recipe."""
    parser = build_parser()
    parsed = parser.parse_args(args)

    if parsed.subcommand == "record":
        return record_command(parsed)
    if parsed.subcommand == "explain":
        return explain_command(parsed)
    if parsed.subcommand == "verify":
        return verify_command(parsed)

    return 0


if __name__ == "__main__":
    sys.exit(main())
