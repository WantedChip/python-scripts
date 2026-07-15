# Recipe Scaler Tool

A Python CLI tool to scale recipe ingredient quantities by a given factor or serving ratio, format numbers as readable mixed fractions or decimals, and handle unit conversions.

## Usage

```bash
# Scale recipe by a factor of 1.5
python recipe_scaler.py path/to/recipe.txt -f 1.5

# Scale recipe to 6 servings (original servings detected in text or JSON)
python recipe_scaler.py path/to/recipe.txt -s 6

# Scale recipe and convert units to metric
python recipe_scaler.py path/to/recipe.txt -f 2.0 -u metric

# Scale a JSON formatted recipe
python recipe_scaler.py path/to/recipe.json -f 0.5
```

## Requirements
- Python 3.8+ (zero external dependencies)

## Notes
- Supports mixed fractions (e.g., `1 1/2`), decimals (e.g., `0.75`), simple fractions (e.g., `1/3`), and quantity ranges (e.g., `1-2` or `1 to 2`).
- Automatically handles unit conversions and formatting (e.g., converting 3 tsp to 1 tbsp, or scaling and rendering 1.2 liters from cups in metric mode).
- Auto-pluralizes and singularizes scaled units for natural output (e.g., `1 cup` scaled by 2 becomes `2 cups`).

## Quality
Quality: pylint 10.00/10 · 82% coverage · 0 dependencies
