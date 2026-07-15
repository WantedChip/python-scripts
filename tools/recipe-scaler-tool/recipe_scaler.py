"""Recipe Scaler Tool.

Scales recipe ingredient quantities by a given factor or target servings,
formats numbers as readable fractions, and handles unit conversions.
"""

import argparse
import json
import re
import sys

# pylint: disable=duplicate-code,too-many-locals
from fractions import Fraction
from typing import Dict, Optional, Tuple

# Volume conversion factors to ml
VOLUME_CONVERSIONS: Dict[str, float] = {
    "tsp": 5.0,
    "teaspoon": 5.0,
    "teaspoons": 5.0,
    "tbsp": 15.0,
    "tablespoon": 15.0,
    "tablespoons": 15.0,
    "cup": 240.0,
    "cups": 240.0,
    "fl oz": 30.0,
    "fluid ounce": 30.0,
    "fluid ounces": 30.0,
    "ml": 1.0,
    "milliliter": 1.0,
    "milliliters": 1.0,
    "l": 1000.0,
    "liter": 1000.0,
    "liters": 1000.0,
}

# Weight conversion factors to g
WEIGHT_CONVERSIONS: Dict[str, float] = {
    "oz": 28.35,
    "ounce": 28.35,
    "ounces": 28.35,
    "lb": 453.59,
    "lbs": 453.59,
    "pound": 453.59,
    "pounds": 453.59,
    "g": 1.0,
    "gram": 1.0,
    "grams": 1.0,
    "kg": 1000.0,
    "kilogram": 1000.0,
    "kilograms": 1000.0,
}


def parse_fraction(val_str: str) -> Fraction:
    """Parses a quantity string (int, float, fraction, mixed fraction) to Fraction.

    Args:
        val_str: The quantity string (e.g., '1 1/2', '0.75', '2').

    Returns:
        A Fraction representing the parsed quantity.
    """
    val_str = val_str.strip()
    if not val_str:
        return Fraction(0)

    # Check for mixed fraction like "1 1/2" or "1-1/2"
    val_str = val_str.replace("-", " ")
    if " " in val_str:
        parts = [p for p in val_str.split(" ") if p]
        if len(parts) == 2:
            try:
                whole = int(parts[0])
                frac = Fraction(parts[1])
                return Fraction(whole) + frac
            except ValueError:
                pass

    try:
        if "/" in val_str:
            return Fraction(val_str)
        # Handles floats like '1.5' and ints like '2'
        return Fraction(val_str)
    except ValueError as err:
        raise ValueError(f"Could not parse quantity: {val_str}") from err


def format_quantity(qty: Fraction, decimals: bool = False) -> str:
    """Formats a Fraction into a human-readable mixed fraction or decimal.

    Args:
        qty: The Fraction to format.
        decimals: If True, returns a decimal string.

    Returns:
        Formatted quantity string.
    """
    # pylint: disable=too-many-return-statements
    if qty == 0:
        return ""

    val = float(qty)
    if val.is_integer():
        return str(int(val))

    if decimals:
        return f"{val:.2f}".rstrip("0").rstrip(".")

    # Handle mixed fraction formatting
    # If the denominator is not standard (not 2, 3, 4, 8, 16), round to nearest standard
    whole = int(val)
    frac_part = val - whole

    if qty.denominator in (2, 3, 4, 8, 16):
        rem = qty.numerator % qty.denominator
        if whole > 0:
            return f"{whole} {rem}/{qty.denominator}"
        return f"{rem}/{qty.denominator}"

    # Rounding algorithm to nearest standard fraction (denominators: 2, 3, 4, 8)
    best_diff = 1.0
    best_num = 0
    best_den = 1

    for den in (2, 3, 4, 8):
        for num in range(den + 1):
            diff = abs(frac_part - num / den)
            if diff < best_diff:
                best_diff = diff
                best_num = num
                best_den = den

    # Also check boundary values (0 and 1)
    if frac_part < best_diff:
        best_diff = frac_part
        best_num = 0
        best_den = 1
    if (1.0 - frac_part) < best_diff:
        best_diff = 1.0 - frac_part
        best_num = 1
        best_den = 1

    if best_den == 1 or best_num == 0 or best_num == best_den:
        final_val = whole + (1 if best_num == best_den else 0)
        return str(final_val) if final_val > 0 else ""

    if whole > 0:
        return f"{whole} {best_num}/{best_den}"
    return f"{best_num}/{best_den}"


def adjust_pluralization(qty: Fraction, unit: str) -> str:
    """Adjusts unit name spelling based on singular vs plural quantities.

    Args:
        qty: The quantity.
        unit: The unit name.

    Returns:
        Adjusted unit name.
    """
    # pylint: disable=too-many-return-statements,too-many-branches
    if qty > 1:
        if unit == "cup":
            return "cups"
        if unit == "teaspoon":
            return "teaspoons"
        if unit == "tablespoon":
            return "tablespoons"
        if unit == "ounce":
            return "ounces"
        if unit == "pound":
            return "pounds"
        if unit == "liter":
            return "liters"
        if unit == "pinch":
            return "pinches"
        if unit == "clove":
            return "cloves"
        if unit == "slice":
            return "slices"
        if unit == "can":
            return "cans"
        if unit == "pack":
            return "packs"
    elif qty <= 1:
        if unit == "cups":
            return "cup"
        if unit == "teaspoons":
            return "teaspoon"
        if unit == "tablespoons":
            return "tablespoon"
        if unit == "ounces":
            return "ounce"
        if unit == "pounds":
            return "pound"
        if unit == "liters":
            return "liter"
        if unit == "pinches":
            return "pinch"
        if unit == "cloves":
            return "clove"
        if unit == "slices":
            return "slice"
        if unit == "cans":
            return "can"
        if unit == "packs":
            return "pack"
    return unit


def convert_unit(qty: Fraction, unit: str, target_system: str) -> Tuple[Fraction, str]:
    """Converts unit and quantity to the target system (metric or imperial).

    Args:
        qty: The quantity to convert.
        unit: The unit of the quantity.
        target_system: Target system ('metric' or 'imperial').

    Returns:
        A tuple of (converted_quantity, converted_unit).
    """
    # pylint: disable=too-many-return-statements,too-many-branches
    unit_lower = unit.lower()

    if target_system == "metric":
        # Convert to metric base
        if unit_lower in VOLUME_CONVERSIONS:
            ml_val = qty * Fraction(str(VOLUME_CONVERSIONS[unit_lower]))
            if ml_val >= 1000:
                return (ml_val / 1000).limit_denominator(1000), "l"
            return ml_val.limit_denominator(1000), "ml"
        if unit_lower in WEIGHT_CONVERSIONS:
            g_val = qty * Fraction(str(WEIGHT_CONVERSIONS[unit_lower]))
            if g_val >= 1000:
                return (g_val / 1000).limit_denominator(1000), "kg"
            return g_val.limit_denominator(1000), "g"

    elif target_system == "imperial":
        # Convert to imperial base
        if unit_lower in VOLUME_CONVERSIONS:
            # Convert ml/l to imperial
            ml_val = qty * Fraction(str(VOLUME_CONVERSIONS[unit_lower]))
            if ml_val >= 240:
                return (ml_val / 240).limit_denominator(1000), "cups"
            if ml_val >= 30:
                return (ml_val / 30).limit_denominator(1000), "fl oz"
            if ml_val >= 15:
                return (ml_val / 15).limit_denominator(1000), "tbsp"
            return (ml_val / 5).limit_denominator(1000), "tsp"
        if unit_lower in WEIGHT_CONVERSIONS:
            # Convert g/kg to imperial
            g_val = qty * Fraction(str(WEIGHT_CONVERSIONS[unit_lower]))
            if g_val >= Fraction("453.59"):
                return (g_val / Fraction("453.59")).limit_denominator(1000), "lbs"
            return (g_val / Fraction("28.35")).limit_denominator(1000), "oz"

    return qty, unit


def scale_ingredient(
    qty_str: str, unit: Optional[str], name: str, factor: Fraction, target_system: str
) -> Tuple[Fraction, Optional[str], str]:
    """Scales a single ingredient by factor, converting systems if requested.

    Args:
        qty_str: Parsed quantity string.
        unit: Optional unit string.
        name: Ingredient name string.
        factor: Scaling factor.
        target_system: Target system.

    Returns:
        Tuple of (scaled_quantity, final_unit, ingredient_name).
    """
    qty = parse_fraction(qty_str)
    scaled_qty = qty * factor

    final_unit: Optional[str] = None
    if unit and target_system != "none":
        scaled_qty, conv_unit = convert_unit(scaled_qty, unit, target_system)
        final_unit = conv_unit
    else:
        final_unit = unit

    if final_unit:
        final_unit = adjust_pluralization(scaled_qty, final_unit)

    return scaled_qty, final_unit, name


def parse_ingredient_line(
    line: str,
) -> Tuple[Optional[str], Optional[str], str]:
    """Parses a line of recipe text into quantity, unit, and name.

    Args:
        line: The raw recipe line.

    Returns:
        A tuple of (quantity_string, unit_string, description).
    """
    cleaned = line.strip()
    if not cleaned:
        return None, None, ""

    # Known units lists for matching
    units = list(VOLUME_CONVERSIONS.keys()) + list(WEIGHT_CONVERSIONS.keys())
    # Sort by length descending to match longer units first
    units.sort(key=len, reverse=True)

    # Patterns:
    # 1. Mixed numbers: e.g. "1 1/2", "2-3/4", "0.5", "12"
    # 2. Match quantities first
    qty_pattern = r"^(\d+(?:\s+\d+/\d+|\.\d+|/\d+)?)\s*"

    # Match range e.g. "1-2" or "1 to 2"
    range_pattern = (
        r"^(\d+(?:\s+\d+/\d+|\.\d+|/\d+)?)\s*(?:-|to)\s*"
        r"(\d+(?:\s+\d+/\d+|\.\d+|/\d+)?)\s+"
    )
    match_range = re.match(range_pattern, cleaned, re.IGNORECASE)
    if match_range:
        rest = cleaned[match_range.end() :]  # noqa: E203
        rest = rest.strip()
        q1, q2 = match_range.group(1), match_range.group(2)
        unit_match = None
        for u in units:
            if rest.lower().startswith(u) and (
                len(rest) == len(u) or rest[len(u)].isspace()
            ):
                unit_match = rest[: len(u)]
                rest = rest[len(u) :]  # noqa: E203
                rest = rest.strip()
                break
        return f"{q1}-{q2}", unit_match, rest

    qty_match = re.match(qty_pattern, cleaned)
    if qty_match:
        q1 = qty_match.group(1)
        rest = cleaned[qty_match.end() :]  # noqa: E203
        rest = rest.strip()
        unit_match = None
        for u in units:
            if rest.lower().startswith(u) and (
                len(rest) == len(u) or rest[len(u)].isspace()
            ):
                unit_match = rest[: len(u)]
                rest = rest[len(u) :]  # noqa: E203
                rest = rest.strip()
                break
        return q1, unit_match, rest

    return None, None, cleaned


def scale_recipe_text(
    recipe_text: str, factor: Fraction, target_system: str, decimals: bool
) -> str:
    """Parses, scales, and formats a full recipe text.

    Args:
        recipe_text: Raw text of the recipe.
        factor: Scaling factor.
        target_system: Target unit system ('metric', 'imperial', 'none').
        decimals: Output formatting style.

    Returns:
        Scaled recipe text.
    """
    # pylint: disable=too-many-locals
    lines = recipe_text.splitlines()
    scaled_lines = []

    in_ingredients = False

    for line in lines:
        stripped = line.strip()

        # Simple heuristic to detect section headings
        if stripped.lower().startswith(
            ("ingredients", "what you need", "shopping list")
        ) or (stripped.endswith(":") and "instruction" not in stripped.lower()):
            in_ingredients = True
            scaled_lines.append(line)
            continue

        if stripped.lower().startswith(
            ("instructions", "directions", "steps", "method")
        ):
            in_ingredients = False
            scaled_lines.append(line)
            continue

        if in_ingredients and stripped:
            qty_str, unit, name = parse_ingredient_line(line)
            if qty_str:
                # Handle ranges e.g. "1-2"
                if "-" in qty_str:
                    q1, q2 = qty_str.split("-")
                    try:
                        sq1, u1, _ = scale_ingredient(
                            q1, unit, name, factor, target_system
                        )
                        sq2, _, _ = scale_ingredient(
                            q2, unit, name, factor, target_system
                        )
                        f_q1 = format_quantity(sq1, decimals)
                        f_q2 = format_quantity(sq2, decimals)
                        unit_str = f" {u1}" if u1 else ""
                        scaled_lines.append(f"{f_q1}-{f_q2}{unit_str} {name}")
                    except ValueError:
                        scaled_lines.append(line)
                else:
                    try:
                        sq, u, _ = scale_ingredient(
                            qty_str, unit, name, factor, target_system
                        )
                        f_q = format_quantity(sq, decimals)
                        unit_str = f" {u}" if u else ""
                        scaled_lines.append(f"{f_q}{unit_str} {name}")
                    except ValueError:
                        scaled_lines.append(line)
            else:
                scaled_lines.append(line)
        else:
            scaled_lines.append(line)

    return "\n".join(scaled_lines)


def scale_recipe_json(
    recipe_json: str, factor: Fraction, target_system: str, decimals: bool
) -> str:
    """Scales a JSON formatted recipe.

    Args:
        recipe_json: JSON string of the recipe.
        factor: Scaling factor.
        target_system: Target unit system.
        decimals: Decimal formatting flag.

    Returns:
        Scaled JSON string.
    """
    try:
        data = json.loads(recipe_json)
    except json.JSONDecodeError as err:
        raise ValueError(f"Invalid JSON: {err}") from err

    # We expect JSON to have an "ingredients" list
    # e.g., {"title": "Cake", "servings": 4, "ingredients": [
    #        {"quantity": "1 1/2", "unit": "cups", "name": "flour"}]}
    # pylint: disable=too-many-nested-blocks
    if "servings" in data and isinstance(data["servings"], (int, float)):
        data["original_servings"] = data["servings"]
        data["servings"] = float(Fraction(data["servings"]) * factor)

    if "ingredients" in data and isinstance(data["ingredients"], list):
        scaled_ingredients = []
        for ing in data["ingredients"]:
            if isinstance(ing, dict) and "name" in ing:
                qty_val = ing.get("quantity")
                unit_val = ing.get("unit")
                name_val = ing.get("name", "")

                if qty_val:
                    try:
                        sq, u, _ = scale_ingredient(
                            str(qty_val), unit_val, name_val, factor, target_system
                        )
                        ing_copy = dict(ing)
                        ing_copy["quantity"] = format_quantity(sq, decimals)
                        if u is not None:
                            ing_copy["unit"] = u
                        scaled_ingredients.append(ing_copy)
                    except ValueError:
                        scaled_ingredients.append(ing)
                else:
                    scaled_ingredients.append(ing)
            else:
                scaled_ingredients.append(ing)
        data["ingredients"] = scaled_ingredients

    return json.dumps(data, indent=2)


def main() -> None:
    """CLI entry point for scaling recipes."""
    # pylint: disable=too-many-statements,too-many-branches
    parser = argparse.ArgumentParser(
        description="Scale recipe ingredients by a factor or serving ratio."
    )
    parser.add_argument("recipe_file", help="Path to recipe file (TXT or JSON format).")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "-f", "--factor", type=float, help="Scaling factor (e.g., 2.0, 0.5)."
    )
    group.add_argument("-s", "--servings", type=int, help="Target servings count.")
    parser.add_argument(
        "-o",
        "--original-servings",
        type=int,
        help="Original servings (required with -s/--servings if not in recipe).",
    )
    parser.add_argument(
        "-u",
        "--unit-system",
        choices=["metric", "imperial", "none"],
        default="none",
        help="Target unit system conversion.",
    )
    parser.add_argument(
        "--decimals",
        action="store_true",
        help="Output quantities as decimals instead of mixed fractions.",
    )
    parser.add_argument(
        "--format",
        choices=["text", "json"],
        help="Override output format detection (default: detect from filename).",
    )

    args = parser.parse_args()

    # Read recipe file
    try:
        with open(args.recipe_file, "r", encoding="utf-8") as file:
            content = file.read()
    except FileNotFoundError:
        print(f"Error: File '{args.recipe_file}' not found.", file=sys.stderr)
        sys.exit(1)
    except IOError as err:
        print(f"Error reading file: {err}", file=sys.stderr)
        sys.exit(1)

    # Determine format
    fmt = args.format
    if not fmt:
        if args.recipe_file.endswith(".json"):
            fmt = "json"
        else:
            fmt = "text"

    # Calculate scaling factor
    factor = Fraction(1)
    if args.factor:
        factor = Fraction(args.factor)
    elif args.servings:
        # Determine original servings
        orig_servings = args.original_servings
        if not orig_servings and fmt == "json":
            try:
                data = json.loads(content)
                orig_servings = data.get("servings")
            except json.JSONDecodeError:
                pass

        if not orig_servings:
            # Try to search for servings in text
            match = re.search(
                r"(?:serves|servings|yields?):\s*(\d+)", content, re.IGNORECASE
            )
            if match:
                orig_servings = int(match.group(1))

        if not orig_servings:
            print(
                "Error: Original servings could not be determined. "
                "Provide --original-servings.",
                file=sys.stderr,
            )
            sys.exit(1)

        factor = Fraction(args.servings, orig_servings)

    # Perform scaling
    try:
        if fmt == "json":
            result = scale_recipe_json(content, factor, args.unit_system, args.decimals)
        else:
            result = scale_recipe_text(content, factor, args.unit_system, args.decimals)
        print(result)
    except ValueError as err:
        print(f"Error: {err}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
