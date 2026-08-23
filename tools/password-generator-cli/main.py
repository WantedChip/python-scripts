"""Password Generator CLI tool.

Cryptographically secure password generator using secrets module with entropy
calculation, customizable character set rules, exclusion options, and memorable
passphrase mode.
"""

# pylint: disable=too-many-branches,too-many-statements
# pylint: disable=too-many-locals,too-many-arguments,too-many-positional-arguments
# pylint: disable=too-many-instance-attributes,too-few-public-methods

import argparse
import math
import secrets
import string
import sys
from typing import List, Optional, Tuple

# Built-in fallback wordlist for passphrase generation (100 memorable words)
DEFAULT_WORDLIST = [
    "amber",
    "anchor",
    "apple",
    "arrow",
    "autumn",
    "badge",
    "beacon",
    "breeze",
    "bridge",
    "cactus",
    "castle",
    "canyon",
    "cedar",
    "cipher",
    "clever",
    "clover",
    "cobalt",
    "comet",
    "crater",
    "crystal",
    "delta",
    "desert",
    "dragon",
    "eagle",
    "echo",
    "ember",
    "falcon",
    "feather",
    "forest",
    "fossil",
    "galaxy",
    "glacier",
    "granite",
    "harbor",
    "haven",
    "hazard",
    "hollow",
    "horizon",
    "island",
    "jasper",
    "jungle",
    "lagoon",
    "lantern",
    "legend",
    "lunar",
    "magnet",
    "marble",
    "meadow",
    "meteor",
    "mirage",
    "mountain",
    "nebula",
    "nectar",
    "oasis",
    "ocean",
    "orchid",
    "origin",
    "palace",
    "panther",
    "pebble",
    "phoenix",
    "planet",
    "plasma",
    "prism",
    "pyramid",
    "quartz",
    "radar",
    "river",
    "rocket",
    "ruby",
    "shadow",
    "shield",
    "signal",
    "silver",
    "solar",
    "spark",
    "sphere",
    "spirit",
    "stone",
    "storm",
    "summit",
    "sunflower",
    "sunset",
    "thunder",
    "timber",
    "titan",
    "topaz",
    "tower",
    "tundra",
    "valley",
    "velvet",
    "vector",
    "vertex",
    "vessel",
    "vortex",
    "walnut",
    "whisper",
    "willow",
    "winter",
    "wisdom",
    "zenith",
    "zephyr",
]


def calculate_entropy(pool_size: int, length: int) -> float:
    """Calculate entropy in bits for a password given pool size and length."""
    if pool_size <= 0 or length <= 0:
        return 0.0
    return length * math.log2(pool_size)


def rate_entropy(entropy_bits: float) -> str:
    """Classify entropy strength rating."""
    if entropy_bits < 40:
        return "Very Weak 🔴"
    if entropy_bits < 60:
        return "Weak 🟠"
    if entropy_bits < 80:
        return "Moderate 🟡"
    if entropy_bits < 120:
        return "Strong 🟢"
    return "Very Strong 🔒"


def generate_password(
    length: int = 16,
    use_upper: bool = True,
    use_lower: bool = True,
    use_digits: bool = True,
    use_symbols: bool = True,
    exclude: str = "",
) -> Tuple[str, float, str]:
    """Generate cryptographically secure random password.

    Returns (password, entropy_bits, strength_rating).
    """
    char_sets: List[str] = []

    if use_lower:
        chars = "".join([c for c in string.ascii_lowercase if c not in exclude])
        if chars:
            char_sets.append(chars)
    if use_upper:
        chars = "".join([c for c in string.ascii_uppercase if c not in exclude])
        if chars:
            char_sets.append(chars)
    if use_digits:
        chars = "".join([c for c in string.digits if c not in exclude])
        if chars:
            char_sets.append(chars)
    if use_symbols:
        chars = "".join([c for c in string.punctuation if c not in exclude])
        if chars:
            char_sets.append(chars)

    if not char_sets:
        err_msg = (
            "At least one character set must be enabled and non-empty after"
            " exclusions."
        )
        raise ValueError(err_msg)

    pool = "".join(char_sets)
    pool_size = len(set(pool))

    length = max(length, len(char_sets))

    # Ensure at least 1 character from each chosen character set
    password_chars = [secrets.choice(c_set) for c_set in char_sets]

    # Fill the remaining length from the full pool
    for _ in range(length - len(password_chars)):
        password_chars.append(secrets.choice(pool))

    # Shuffle securely using secrets
    for i in range(len(password_chars) - 1, 0, -1):
        j = secrets.randbelow(i + 1)
        password_chars[i], password_chars[j] = (
            password_chars[j],
            password_chars[i],
        )

    password = "".join(password_chars)
    entropy = calculate_entropy(pool_size, length)
    rating = rate_entropy(entropy)

    return password, entropy, rating


def generate_passphrase(
    word_count: int = 4,
    separator: str = "-",
    capitalize: bool = True,
    include_number: bool = True,
    wordlist: Optional[List[str]] = None,
) -> Tuple[str, float, str]:
    """Generate a memorable passphrase from a wordlist.

    Returns (passphrase, entropy_bits, strength_rating).
    """
    words_pool = wordlist if wordlist is not None else DEFAULT_WORDLIST
    if not words_pool:
        raise ValueError("Wordlist cannot be empty.")

    selected_words = [secrets.choice(words_pool) for _ in range(word_count)]
    if capitalize:
        selected_words = [w.capitalize() for w in selected_words]

    if include_number:
        digit = str(secrets.randbelow(100))
        selected_words.append(digit)

    passphrase = separator.join(selected_words)

    # Entropy calculation for passphrase
    pool_size = len(set(words_pool))
    entropy = calculate_entropy(pool_size, word_count)
    if include_number:
        entropy += math.log2(100)  # Add 100 possible digits entropy

    rating = rate_entropy(entropy)
    return passphrase, entropy, rating


def build_parser() -> argparse.ArgumentParser:
    """Build CLI parser."""
    desc = "Cryptographically Secure Password Generator CLI"
    parser = argparse.ArgumentParser(description=desc)
    subparsers = parser.add_subparsers(dest="mode", help="Generation mode")

    # Standard Password mode
    pass_parser = subparsers.add_parser(
        "password", help="Generate random character password"
    )
    pass_parser.add_argument(
        "-l",
        "--length",
        type=int,
        default=16,
        help="Password length (default: 16)",
    )
    pass_parser.add_argument(
        "--no-upper", action="store_true", help="Exclude uppercase letters"
    )
    pass_parser.add_argument(
        "--no-lower", action="store_true", help="Exclude lowercase letters"
    )
    pass_parser.add_argument("--no-digits", action="store_true", help="Exclude digits")
    pass_parser.add_argument(
        "--no-symbols", action="store_true", help="Exclude special symbols"
    )
    pass_parser.add_argument(
        "-e",
        "--exclude",
        default="",
        help="Characters to exclude (e.g. 'lI1O0')",
    )

    # Passphrase mode
    phrase_parser = subparsers.add_parser(
        "passphrase", help="Generate memorable word passphrase"
    )
    phrase_parser.add_argument(
        "-w",
        "--words",
        type=int,
        default=4,
        help="Number of words (default: 4)",
    )
    phrase_parser.add_argument(
        "-s",
        "--separator",
        default="-",
        help="Word separator character (default: '-')",
    )
    phrase_parser.add_argument(
        "--no-capitalize", action="store_true", help="Do not capitalize words"
    )
    phrase_parser.add_argument(
        "--no-number", action="store_true", help="Do not append random digits"
    )
    return parser


def main(args: Optional[List[str]] = None) -> int:
    """CLI entrypoint for Password Generator."""
    parser = build_parser()
    parsed = parser.parse_args(args)

    if parsed.mode == "passphrase":
        passphrase, entropy, rating = generate_passphrase(
            word_count=parsed.words,
            separator=parsed.separator,
            capitalize=not parsed.no_capitalize,
            include_number=not parsed.no_number,
        )
        print(f"\n🔐 Passphrase: {passphrase}")
        print(f"📊 Entropy:    {entropy:.1f} bits ({rating})")

    else:
        # Default to password mode
        length = getattr(parsed, "length", 16)
        pwd, entropy, rating = generate_password(
            length=length,
            use_upper=not getattr(parsed, "no_upper", False),
            use_lower=not getattr(parsed, "no_lower", False),
            use_digits=not getattr(parsed, "no_digits", False),
            use_symbols=not getattr(parsed, "no_symbols", False),
            exclude=getattr(parsed, "exclude", ""),
        )
        print(f"\n🔐 Password: {pwd}")
        print(f"📊 Entropy:  {entropy:.1f} bits ({rating})")

    return 0


if __name__ == "__main__":
    sys.exit(main())
