#!/usr/bin/env python3
"""Permission Explainer.

Explains file and directory permission/ACL failures in plain language and
suggests the minimal safe fix for Windows and POSIX environments.
"""

import argparse
import getpass
import os
import re
import stat
import subprocess  # nosec B404
import sys
from typing import List, Tuple


def get_current_user_unix() -> Tuple[str, int, List[int]]:
    """Retrieve username, UID, and supplementary group IDs on Unix."""
    username = getpass.getuser()
    uid = 0
    gids: List[int] = []
    try:
        uid = getattr(os, "getuid", lambda: 0)()
        gids = getattr(os, "getgroups", lambda: [])()
    except (AttributeError, OSError):
        pass
    return username, uid, gids


# pylint: disable=too-many-locals,too-many-branches,too-many-statements
def explain_unix_permissions(
    path: str, operation: str, target_user: str
) -> Tuple[str, str]:
    """Analyze POSIX file modes, ownerships, and groups to diagnose access issues."""
    try:
        info = os.stat(path)
    except OSError as e:
        return f"Error: Cannot access path: {e}", ""

    mode = info.st_mode
    uid = info.st_uid
    gid = info.st_gid

    # Resolve target user
    current_user, current_uid, current_gids = get_current_user_unix()

    # Analyze permissions
    is_owner = target_user == current_user and current_uid == uid
    is_group = gid in current_gids

    # Permission bits mapping
    owner_r = bool(mode & stat.S_IRUSR)
    owner_w = bool(mode & stat.S_IWUSR)
    owner_x = bool(mode & stat.S_IXUSR)

    group_r = bool(mode & stat.S_IRGRP)
    group_w = bool(mode & stat.S_IWGRP)
    group_x = bool(mode & stat.S_IXGRP)

    other_r = bool(mode & stat.S_IROTH)
    other_w = bool(mode & stat.S_IWOTH)
    other_x = bool(mode & stat.S_IXOTH)

    explanation = []
    oct_mode = oct(stat.S_IMODE(mode))
    explanation.append(
        f"POSIX file mode: {oct_mode} (Owner UID: {uid}, Group GID: {gid})"
    )

    if is_owner:
        explanation.append(f"Active user '{target_user}' is the OWNER of this file.")
        has_r, has_w, has_x = owner_r, owner_w, owner_x
    elif is_group:
        explanation.append(
            f"Active user '{target_user}' belongs to the GROUP associated "
            "with this file."
        )
        has_r, has_w, has_x = group_r, group_w, group_x
    else:
        explanation.append(
            f"Active user '{target_user}' is classified as OTHER (neither owner "
            "nor group member)."
        )
        has_r, has_w, has_x = other_r, other_w, other_x

    explanation.append(
        f"Allowed permissions: Read={has_r}, Write={has_w}, Execute={has_x}"
    )

    # Determine status
    allowed = False
    if operation == "read" and has_r:
        allowed = True
    elif operation == "write" and has_w:
        allowed = True
    elif operation == "execute" and has_x:
        allowed = True

    if allowed:
        return (
            "\n".join(explanation)
            + "\nDiagnosis: Access is theoretically ALLOWED. If failing, "
            "check parent directory permissions.",
            "",
        )

    # Generate minimal safe fix
    reasons = f"Access denied: requested '{operation}', but permission is false."
    explanation.append(f"Diagnosis: {reasons}")

    # Recommendation
    fix_cmd = ""
    is_dir = stat.S_ISDIR(mode)
    dir_flag = " -R" if is_dir else ""

    if is_owner:
        if operation == "read":
            fix_cmd = f'chmod u+r{dir_flag} "{path}"'
        elif operation == "write":
            fix_cmd = f'chmod u+w{dir_flag} "{path}"'
        elif operation == "execute":
            fix_cmd = f'chmod u+x{dir_flag} "{path}"'
    else:
        # Suggest chown or chmod other/group
        if operation == "read":
            fix_cmd = (
                f'sudo chown "{target_user}" "{path}" OR chmod o+r{dir_flag} "{path}"'
            )
        elif operation == "write":
            fix_cmd = (
                f'sudo chown "{target_user}" "{path}" OR chmod o+w{dir_flag} "{path}"'
            )
        elif operation == "execute":
            fix_cmd = (
                f'sudo chown "{target_user}" "{path}" OR chmod o+x{dir_flag} "{path}"'
            )

    return "\n".join(explanation), fix_cmd


# pylint: disable=too-many-locals
def explain_windows_permissions(
    path: str, operation: str, target_user: str
) -> Tuple[str, str]:
    """Parse NTFS ACL allocations via icacls command execution."""
    explanation = []

    # Check Read-Only attribute first
    try:
        attrs = os.stat(path)
        is_readonly = not bool(attrs.st_mode & stat.S_IWRITE)
        if is_readonly:
            explanation.append(
                "[System Flag] File is marked as READ-ONLY at filesystem level."
            )
    except OSError as e:
        return f"Error: Cannot access path: {e}", ""

    # Run icacls
    try:
        res = subprocess.run(
            ["icacls", path],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )  # nosec
        icacls_out = res.stdout.strip()
    except OSError:
        icacls_out = "Could not run icacls utility."

    explanation.append("NTFS Access Control List (icacls output):")
    explanation.append(icacls_out)

    # Simple parse heuristics
    user_found = False
    has_write = False
    has_read = False

    user_pattern = re.compile(re.escape(target_user) + r":\(([^)]+)\)", re.IGNORECASE)
    matches = user_pattern.findall(icacls_out)
    if matches:
        user_found = True
        perms = ",".join(matches).upper()
        if "F" in perms or "M" in perms or "W" in perms:
            has_write = True
        if "F" in perms or "M" in perms or "R" in perms or "RX" in perms:
            has_read = True
        explanation.append(
            f"NTFS matching permissions for user '{target_user}': {perms}"
        )
    else:
        explanation.append(
            f"User '{target_user}' not explicitly listed in icacls entries."
        )

    # Output diagnosis
    op_ok = (
        (operation == "read" and has_read)
        or (operation == "write" and has_write and not is_readonly)
        or (operation == "execute" and has_read)
    )
    if user_found and op_ok:
        explanation.append("Diagnosis: Access appears to be ALLOWED under NTFS ACLs.")

    # Generate minimal safe fix
    fix_cmd = ""
    if operation == "write":
        if is_readonly:
            fix_cmd = f'attrib -R "{path}"\n'
        fix_cmd += f'icacls "{path}" /grant "{target_user}":W'
    elif operation == "read":
        fix_cmd = f'icacls "{path}" /grant "{target_user}":R'
    elif operation == "execute":
        fix_cmd = f'icacls "{path}" /grant "{target_user}":RX'

    return "\n".join(explanation), fix_cmd


def main() -> None:
    """CLI Entrypoint."""
    parser = argparse.ArgumentParser(
        description=(
            "Explain Unix/Windows file-permission issues and suggest minimal safe "
            "fixes."
        )
    )
    parser.add_argument("path", help="Target file or directory path to inspect.")
    parser.add_argument(
        "-o",
        "--operation",
        choices=["read", "write", "execute"],
        default="read",
        help="Target operation being audited (default: read).",
    )
    parser.add_argument(
        "-u", "--user", help="Target system user (defaults to current system login)."
    )

    args = parser.parse_args()

    if not os.path.exists(args.path):
        print(f"Error: Path does not exist: {args.path}", file=sys.stderr)
        sys.exit(1)

    target_user = args.user or getpass.getuser()

    print("========================================================================")
    print("PERMISSION EXPLAINER DIAGNOSTIC LOG")
    print("========================================================================")
    print(f"File Path: {os.path.abspath(args.path)}")
    print(f"Operation: {args.operation.upper()}")
    print(f"User Name: {target_user}")
    print("-" * 80)

    # Perform OS-specific analysis
    if sys.platform == "win32":
        expl, fix = explain_windows_permissions(args.path, args.operation, target_user)
    else:
        expl, fix = explain_unix_permissions(args.path, args.operation, target_user)

    print(expl)
    print("=" * 80)
    if fix:
        print("RECOMMENDED MINIMAL SAFE FIX:")
        print(fix)
    else:
        print(
            "No immediate permission fix recommended. User is already configured "
            "with access."
        )
    print("=" * 80)


if __name__ == "__main__":
    main()
