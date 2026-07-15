"""env-diff: Compares local environment snapshots to debug reproducibility bugs.

Allows capturing local OS/python/package/binary environments as a JSON snapshot,
and comparing two snapshots (or a remote snapshot against the current machine)
to explain execution discrepancies.
"""

import argparse
import ctypes
import importlib.metadata
import json
import os
import platform
import shutil
import sys
from typing import Any, Dict

SENSITIVE_KEYWORDS = {
    "KEY",
    "PASS",
    "SECRET",
    "TOKEN",
    "AUTH",
    "PWD",
    "SIGNATURE",
    "CERT",
    "CREDENTIAL",
    "DATABASE",
    "CONN",
}


def sanitize_env(env: Dict[str, str]) -> Dict[str, str]:
    """Mask values of environment variables containing credentials.

    Args:
        env: Environment variable mappings.

    Returns:
        Sanitized environment mappings.
    """
    sanitized = {}
    for k, v in env.items():
        k_upper = k.upper()
        if any(kw in k_upper for kw in SENSITIVE_KEYWORDS):
            sanitized[k] = "[SANITIZED]"
        else:
            sanitized[k] = v
    return sanitized


def is_privileged() -> bool:
    """Check if the current process runs with administrative/root privileges.

    Returns:
        True if running with administrator/root privileges, False otherwise.
    """
    if sys.platform == "win32":
        try:
            windll = getattr(ctypes, "windll", None)
            if windll:
                return bool(windll.shell32.IsUserAnAdmin() != 0)
            return False
        except Exception:  # pylint: disable=broad-except
            return False
    else:
        try:
            # pylint: disable=no-member
            return bool(os.getuid() == 0)
        except Exception:  # pylint: disable=broad-except
            return False


def capture_snapshot() -> Dict[str, Any]:
    """Generate a dictionary detailing the local environment state.

    Returns:
        A dictionary containing environment details.
    """
    # 1. OS details
    os_details = {
        "system": platform.system(),
        "release": platform.release(),
        "machine": platform.machine(),
        "architecture": platform.architecture()[0],
    }

    # 2. Python details
    py_details = {
        "version": platform.python_version(),
        "implementation": platform.python_implementation(),
        "executable": sys.executable,
    }

    # 3. Environment variables (sanitized)
    env_vars = sanitize_env(dict(os.environ))

    # 4. Installed Packages
    packages = {}
    for dist in importlib.metadata.distributions():
        try:
            name = dist.metadata["Name"]
            if name:
                packages[name.lower().replace("-", "_")] = dist.version
        except Exception:  # pylint: disable=broad-except  # nosec B110
            pass

    # 5. Reachable Binaries
    common_binaries = [
        "git",
        "docker",
        "node",
        "npm",
        "yarn",
        "pnpm",
        "gcc",
        "python",
        "pip",
        "make",
        "curl",
        "wget",
    ]
    binaries = {}
    for b in common_binaries:
        which_path = shutil.which(b)
        binaries[b] = which_path if which_path else None

    # 6. PATH directories
    path_env = os.environ.get("PATH", "")
    path_dirs = [d for d in path_env.split(os.pathsep) if d]

    return {
        "os": os_details,
        "python": py_details,
        "env": env_vars,
        "packages": packages,
        "binaries": binaries,
        "path_dirs": path_dirs,
        "privileged": is_privileged(),
    }


class EnvDiff:
    # pylint: disable=too-few-public-methods
    """Computes comparison maps between two environment snapshots."""

    def __init__(self, ref: Dict[str, Any], target: Dict[str, Any]) -> None:
        """Initialize the comparison.

        Args:
            ref: Snapshot dictionary of the working machine.
            target: Snapshot dictionary of the failing machine.
        """
        self.ref = ref
        self.target = target

    def compare(self) -> Dict[str, Any]:
        # pylint: disable=too-many-locals
        """Verify discrepancies across python/OS/package definitions.

        Returns:
            Dictionary containing diff details and diagnostics.
        """
        diffs: Dict[str, Any] = {
            "os_mismatch": {},
            "python_mismatch": {},
            "missing_packages": [],
            "package_version_mismatches": {},
            "missing_binaries": [],
            "missing_env_vars": [],
            "env_var_mismatches": {},
            "privilege_mismatch": None,
        }

        # 1. Compare OS
        for k in ("system", "machine"):
            ref_val = self.ref.get("os", {}).get(k)
            t_val = self.target.get("os", {}).get(k)
            if ref_val != t_val:
                diffs["os_mismatch"][k] = {"working": ref_val, "failing": t_val}

        # 2. Compare Python
        ref_py = self.ref.get("python", {}).get("version", "")
        t_py = self.target.get("python", {}).get("version", "")
        # Compare major/minor
        ref_py_short = ".".join(ref_py.split(".")[:2])
        t_py_short = ".".join(t_py.split(".")[:2])
        if ref_py_short != t_py_short:
            diffs["python_mismatch"]["version"] = {
                "working": ref_py,
                "failing": t_py,
            }

        # 3. Compare Packages
        ref_pkgs = self.ref.get("packages", {})
        t_pkgs = self.target.get("packages", {})
        for pkg, v_ref in ref_pkgs.items():
            if pkg not in t_pkgs:
                diffs["missing_packages"].append(pkg)
            elif t_pkgs[pkg] != v_ref:
                diffs["package_version_mismatches"][pkg] = {
                    "working": v_ref,
                    "failing": t_pkgs[pkg],
                }

        # 4. Compare Binaries
        ref_bins = self.ref.get("binaries", {})
        t_bins = self.target.get("binaries", {})
        for b, path_ref in ref_bins.items():
            if path_ref and not t_bins.get(b):
                diffs["missing_binaries"].append(b)

        # 5. Compare Env Vars
        ref_envs = self.ref.get("env", {})
        t_envs = self.target.get("env", {})
        for k, v_ref in ref_envs.items():
            if k not in t_envs:
                diffs["missing_env_vars"].append(k)
            elif (
                v_ref != "[SANITIZED]"
                and t_envs[k] != "[SANITIZED]"
                and t_envs[k] != v_ref
            ):
                diffs["env_var_mismatches"][k] = {
                    "working": v_ref,
                    "failing": t_envs[k],
                }

        # 6. Compare Privileged
        ref_priv = self.ref.get("privileged")
        t_priv = self.target.get("privileged")
        if ref_priv is not None and t_priv is not None and ref_priv != t_priv:
            diffs["privilege_mismatch"] = {
                "working": ref_priv,
                "failing": t_priv,
            }

        return diffs


def render_diff(diffs: Dict[str, Any]) -> None:
    # pylint: disable=too-many-branches,too-many-statements
    """Print environment diagnostic discrepancy reports.

    Args:
        diffs: Computed differences dictionary.
    """
    print("\n" + "=" * 65)
    print("                    ENVIRONMENT DIFF REPORT")
    print("=" * 65)

    has_diffs = False

    # OS Differences
    if diffs["os_mismatch"]:
        has_diffs = True
        print("\n[⚠️] OS/Architecture Mismatches:")
        for k, v in diffs["os_mismatch"].items():
            print(
                f"  - {k.capitalize()}: Working uses '{v['working']}', "
                f"but failing uses '{v['failing']}'"
            )

    # Python Differences
    if diffs["python_mismatch"]:
        has_diffs = True
        print("\n[⚠️] Python Version Mismatch:")
        v = diffs["python_mismatch"]["version"]
        print(
            f"  - Python Version: Working uses '{v['working']}', "
            f"but failing uses '{v['failing']}'"
        )

    # Missing Packages
    if diffs["missing_packages"]:
        has_diffs = True
        print("\n[⚠️] Missing Python Packages on Failing Machine:")
        for pkg in sorted(diffs["missing_packages"]):
            print(f"  - {pkg}")

    # Package Version Mismatches
    if diffs["package_version_mismatches"]:
        has_diffs = True
        print("\n[⚠️] Python Package Version Mismatches:")
        for pkg, v in sorted(diffs["package_version_mismatches"].items()):
            print(
                f"  - {pkg}: Working version '{v['working']}', "
                f"but failing version '{v['failing']}'"
            )

    # Missing Binaries
    if diffs["missing_binaries"]:
        has_diffs = True
        print("\n[⚠️] Missing Command Line Binaries on Failing Machine:")
        for b in sorted(diffs["missing_binaries"]):
            print(f"  - {b} (Is present in Working system PATH)")

    # Missing Env Vars
    if diffs["missing_env_vars"]:
        has_diffs = True
        print("\n[⚠️] Missing Environment Variables on Failing Machine:")
        for k in sorted(diffs["missing_env_vars"]):
            print(f"  - {k}")

    # Env Var Mismatches
    if diffs["env_var_mismatches"]:
        has_diffs = True
        print("\n[⚠️] Environment Variable Value Mismatches:")
        for k, v in sorted(diffs["env_var_mismatches"].items()):
            print(
                f"  - {k}: Working value '{v['working']}', "
                f"but failing value '{v['failing']}'"
            )

    # Privilege mismatch
    if diffs["privilege_mismatch"]:
        has_diffs = True
        print("\n[⚠️] Privilege Level Mismatch:")
        v = diffs["privilege_mismatch"]
        print(
            f"  - Admin/Root Privileges: Working requires '{v['working']}', "
            f"but failing runs as '{v['failing']}'"
        )

    if not has_diffs:
        print("\nNo critical environment discrepancies detected.")
        print("Both snapshot environments match closely.")
    else:
        print("\n--- Diagnostic Remediation Explanations ---")
        remediations = []
        if diffs["missing_packages"]:
            remediations.append(
                "Run 'pip install -r requirements.txt' or install missing "
                "modules in the failing environment."
            )
        if diffs["package_version_mismatches"]:
            remediations.append(
                "Sync python package versions: mismatch might cause "
                "incompatible library API exceptions."
            )
        if diffs["missing_binaries"]:
            remediations.append(
                "Install missing external system binaries (e.g. Docker, "
                "Node, or compiler tools) on the failing machine."
            )
        if diffs["missing_env_vars"]:
            remediations.append(
                "Copy missing environment variable declarations from working "
                "setup to target setup."
            )
        if diffs["privilege_mismatch"]:
            remediations.append(
                "Re-run command shell with administrative permissions (Admin/Sudo)."
            )

        if remediations:
            for idx, r in enumerate(remediations, 1):
                print(f"{idx}. {r}")
        else:
            print("Verify configuration parameters or local script setup.")

    print("=" * 65)


def main() -> None:
    """Main CLI entrypoint."""
    parser = argparse.ArgumentParser(
        description="Diagnose environment differences between system snapshots."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # Subcommand 1: snapshot
    snap_parser = subparsers.add_parser(
        "snapshot", help="Capture local system environment."
    )
    snap_parser.add_argument("output", help="Output path to write snapshot JSON.")

    # Subcommand 2: compare
    comp_parser = subparsers.add_parser("compare", help="Compare two saved snapshots.")
    comp_parser.add_argument("working", help="JSON snapshot of working machine.")
    comp_parser.add_argument("failing", help="JSON snapshot of failing machine.")

    # Subcommand 3: auto
    auto_parser = subparsers.add_parser(
        "auto", help="Compare local machine to a reference snapshot."
    )
    auto_parser.add_argument(
        "working", help="JSON snapshot of reference working machine."
    )

    args = parser.parse_args()

    if args.command == "snapshot":
        snap = capture_snapshot()
        try:
            with open(args.output, "w", encoding="utf-8") as f:
                json.dump(snap, f, indent=2)
            print(f"Environment snapshot successfully saved to: {args.output}")
        except OSError as e:
            print(f"Error writing snapshot: {str(e)}")
            sys.exit(1)

    elif args.command == "compare":
        try:
            with open(args.working, "r", encoding="utf-8") as f:
                w_snap = json.load(f)
            with open(args.failing, "r", encoding="utf-8") as f:
                f_snap = json.load(f)
        except (OSError, json.JSONDecodeError) as e:
            print(f"Error reading snapshot files: {str(e)}")
            sys.exit(1)

        differ = EnvDiff(w_snap, f_snap)
        diffs = differ.compare()
        render_diff(diffs)

    elif args.command == "auto":
        try:
            with open(args.working, "r", encoding="utf-8") as f:
                w_snap = json.load(f)
        except (OSError, json.JSONDecodeError) as e:
            print(f"Error reading working snapshot file: {str(e)}")
            sys.exit(1)

        f_snap = capture_snapshot()
        differ = EnvDiff(w_snap, f_snap)
        diffs = differ.compare()
        render_diff(diffs)


if __name__ == "__main__":
    main()
