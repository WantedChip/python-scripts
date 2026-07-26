"""Environment Variable Exporter.

Filters and exports OS environment variables into a clean, sanitized .env file
for project setup and environment template generation. Supports prefix matching
and secret masking.
"""

# pylint: disable=too-many-branches,too-many-statements
# pylint: disable=too-many-locals,too-many-arguments,too-many-positional-arguments
# pylint: disable=too-many-instance-attributes,too-few-public-methods

import argparse
import os
import re
import sys
from typing import Dict, List, Optional, Set

SECRET_KEYWORDS = {
    "SECRET",
    "PASSWORD",
    "PASS",
    "KEY",
    "TOKEN",
    "CREDENTIAL",
    "AUTH",
    "PRIVATE",
    "SALT",
}


def is_secret_key(key: str, custom_keywords: Optional[Set[str]] = None) -> bool:
    """Determine if an environment variable key is sensitive/secret."""
    keywords = SECRET_KEYWORDS if custom_keywords is None else custom_keywords
    key_upper = key.upper()
    return any(kw in key_upper for kw in keywords)


def filter_environment_variables(
    prefix: Optional[str] = None,
    keys: Optional[List[str]] = None,
    include_empty: bool = False,
    environ: Optional[Dict[str, str]] = None,
) -> Dict[str, str]:
    """Filter environment variables matching prefix or specific keys.

    Args:
        prefix: Filter keys starting with prefix.
        keys: Explicit list of keys to export.
        include_empty: Whether to include keys with empty values.
        environ: Dictionary of environment variables (defaults to os.environ).

    Returns:
        Dict[str, str]: Filtered dictionary of key-value pairs.
    """
    env_source = os.environ if environ is None else environ
    result = {}

    target_keys = set(keys) if keys else None

    for key, value in env_source.items():
        if not include_empty and not value.strip():
            continue

        if target_keys is not None:
            if key in target_keys:
                result[key] = value
        elif prefix is not None:
            if key.startswith(prefix):
                result[key] = value
        else:
            # If neither prefix nor explicit keys, return all
            result[key] = value

    return dict(sorted(result.items()))


def sanitize_value(
    key: str,
    value: str,
    mask_secrets: bool = False,
    placeholder: str = "YOUR_VALUE_HERE",
) -> str:
    """Sanitize environment variable value for .env output."""
    if mask_secrets and is_secret_key(key):
        return f"<{placeholder}>"

    # Quote value if it contains whitespace, special characters or equals
    if re.search(r'\s|#|"', value) or value == "":
        escaped_value = value.replace('"', '\\"')
        return f'"{escaped_value}"'

    return value


def generate_env_file_content(
    env_vars: Dict[str, str],
    mask_secrets: bool = False,
    placeholder: str = "YOUR_VALUE_HERE",
    header_comment: Optional[str] = None,
) -> str:
    """Generate sanitized .env file string format."""
    lines = []
    if header_comment:
        lines.append(f"# {header_comment}")
        lines.append("")

    for key, val in env_vars.items():
        sanit_val = sanitize_value(
            key, val, mask_secrets=mask_secrets, placeholder=placeholder
        )
        lines.append(f"{key}={sanit_val}")

    return "\n".join(lines) + "\n"


def export_env_file(
    output_path: str,
    prefix: Optional[str] = None,
    keys: Optional[List[str]] = None,
    mask_secrets: bool = False,
    placeholder: str = "YOUR_VALUE_HERE",
) -> int:
    """Export filtered env vars to file."""
    filtered_vars = filter_environment_variables(prefix=prefix, keys=keys)
    if not filtered_vars:
        msg = (
            "Warning: No environment variables matched filter "
            f"(prefix='{prefix}', keys={keys})"
        )
        print(msg, file=sys.stderr)

    content = generate_env_file_content(
        filtered_vars,
        mask_secrets=mask_secrets,
        placeholder=placeholder,
        header_comment="Auto-generated .env configuration file",
    )

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(content)

    msg_ok = (
        f"Successfully exported {len(filtered_vars)} variable(s) to '{output_path}'"
    )
    print(msg_ok)
    return len(filtered_vars)


def build_parser() -> argparse.ArgumentParser:
    """Build CLI parser."""
    parser = argparse.ArgumentParser(description="Environment Variable Exporter")
    parser.add_argument(
        "-o",
        "--output",
        default=".env",
        help="Output file path (default: .env)",
    )
    parser.add_argument(
        "-p",
        "--prefix",
        help="Filter variables by key prefix (e.g. APP_)",
    )
    parser.add_argument("-k", "--keys", nargs="+", help="Specific key names to export")
    parser.add_argument(
        "-m",
        "--mask-secrets",
        action="store_true",
        help="Mask sensitive secret values",
    )
    parser.add_argument(
        "--placeholder",
        default="YOUR_VALUE_HERE",
        help="Placeholder text for masked secrets",
    )
    return parser


def main(args: Optional[List[str]] = None) -> int:
    """CLI entrypoint."""
    parser = build_parser()
    parsed = parser.parse_args(args)

    export_env_file(
        output_path=parsed.output,
        prefix=parsed.prefix,
        keys=parsed.keys,
        mask_secrets=parsed.mask_secrets,
        placeholder=parsed.placeholder,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
