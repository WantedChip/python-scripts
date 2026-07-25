# Cocktail Recipe Fetcher

A Python CLI tool to search cocktail recipes by name, filter by ingredient, or fetch random drinks using TheCocktailDB API.

## Features
- Search cocktails by drink name.
- Filter drinks containing a specific ingredient (e.g., Gin, Tequila).
- Fetch a random cocktail recipe.
- Formats ingredients, measurements, and instructions into a terminal card.
- Export recipes to JSON.

## Usage

```bash
# Search for Margarita
python main.py --name margarita

# Find drinks made with Gin
python main.py --ingredient gin

# Fetch a random cocktail
python main.py --random

# Save recipe to JSON
python main.py --name mojito --json mojito.json
```
