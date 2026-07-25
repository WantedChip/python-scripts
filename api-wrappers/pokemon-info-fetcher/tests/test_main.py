"""Unit tests for Pokémon Info Fetcher."""

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from main import (
    export_json,
    fetch_evolution_chain,
    fetch_pokemon_data,
    format_pokemon_card,
)


class TestPokemonFetcher(unittest.TestCase):
    """Test suite for Pokémon info fetcher functions."""

    def setUp(self) -> None:
        self.sample_pokemon = {
            "id": 25,
            "name": "pikachu",
            "height": 4,
            "weight": 60,
            "types": [{"type": {"name": "electric"}}],
            "abilities": [{"ability": {"name": "static"}}],
            "stats": [
                {"stat": {"name": "hp"}, "base_stat": 35},
                {"stat": {"name": "attack"}, "base_stat": 55},
            ],
            "sprites": {
                "front_default": (
                    "https://raw.githubusercontent.com/PokeAPI/"
                    "sprites/master/sprites/pokemon/25.png"
                )
            },
            "species": {"url": "https://pokeapi.co/api/v2/pokemon-species/25/"},
        }

    @patch("main.fetch_json")
    def test_fetch_pokemon_data_success(self, mock_fetch: MagicMock) -> None:
        """Test successfully fetching pokemon data."""
        mock_fetch.return_value = self.sample_pokemon
        result = fetch_pokemon_data("pikachu")
        self.assertIsNotNone(result)
        self.assertEqual(result["id"], 25)
        mock_fetch.assert_called_once_with("https://pokeapi.co/api/v2/pokemon/pikachu")

    @patch("main.fetch_json")
    def test_fetch_pokemon_data_not_found(self, mock_fetch: MagicMock) -> None:
        """Test handling missing or non-existent pokemon."""
        mock_fetch.return_value = None
        result = fetch_pokemon_data("invalid_name")
        self.assertIsNone(result)

    @patch("main.fetch_json")
    def test_fetch_evolution_chain(self, mock_fetch: MagicMock) -> None:
        """Test extracting evolution chain names."""
        species_resp = {
            "evolution_chain": {"url": "https://pokeapi.co/api/v2/evolution-chain/10/"}
        }
        evo_resp = {
            "chain": {
                "species": {"name": "pichu"},
                "evolves_to": [
                    {
                        "species": {"name": "pikachu"},
                        "evolves_to": [
                            {"species": {"name": "raichu"}, "evolves_to": []}
                        ],
                    }
                ],
            }
        }
        mock_fetch.side_effect = [species_resp, evo_resp]
        evolutions = fetch_evolution_chain(
            "https://pokeapi.co/api/v2/pokemon-species/25/"
        )
        self.assertEqual(evolutions, ["Pichu", "Pikachu", "Raichu"])

    def test_format_pokemon_card(self) -> None:
        """Test formatting Pokémon card output string."""
        card = format_pokemon_card(self.sample_pokemon, ["Pichu", "Pikachu", "Raichu"])
        self.assertIn("PIKACHU", card)
        self.assertIn("Electric", card)
        self.assertIn("0.4 m", card)
        self.assertIn("6.0 kg", card)
        self.assertIn("Pichu -> Pikachu -> Raichu", card)

    def test_export_json(self) -> None:
        """Test exporting Pokémon data to JSON file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            file_path = str(Path(tmpdir) / "output.json")
            success = export_json(self.sample_pokemon, ["Pichu", "Pikachu"], file_path)
            self.assertTrue(success)
            with open(file_path, "r", encoding="utf-8") as f:
                content = json.load(f)
            self.assertEqual(content["name"], "pikachu")
            self.assertEqual(content["height_m"], 0.4)


if __name__ == "__main__":
    unittest.main()
