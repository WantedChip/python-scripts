# Pokémon Info Fetcher

A Python CLI tool to query Pokémon stats, types, abilities, sprite URLs, and evolution chains from PokéAPI (`pokeapi.co`).

## Features
- Search Pokémon by name or Pokedex ID.
- Resolves evolution chains automatically.
- Formats base stats and metadata into a terminal stat card.
- Export structured data to JSON.

## Usage

```bash
# Display terminal stat card for Pikachu
python main.py pikachu

# Look up by ID and export to JSON
python main.py 150 --json mewtwo.json

# View raw PokéAPI response
python main.py charizard --raw
```
