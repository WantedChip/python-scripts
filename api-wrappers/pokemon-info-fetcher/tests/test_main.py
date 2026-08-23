"""Unit tests for Pokémon Info Fetcher."""

import io
import json
import tempfile
import unittest
import urllib.error
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

from main import (
    export_json,
    fetch_evolution_chain,
    fetch_json,
    fetch_pokemon_data,
    format_pokemon_card,
    main,
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

    def test_export_json_oserror(self) -> None:
        """Unwritable export targets report failure instead of crashing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            bad_path = str(Path(tmpdir) / "missing" / "output.json")
            stderr = io.StringIO()
            with redirect_stderr(stderr):
                success = export_json(self.sample_pokemon, ["Pikachu"], bad_path)
        self.assertFalse(success)
        self.assertIn("Error writing JSON", stderr.getvalue())


class TestNetworkLayer(unittest.TestCase):
    """Tests for the low-level PokéAPI HTTP helper."""

    @patch("main.urllib.request.urlopen")
    def test_fetch_json_success(self, mock_urlopen: MagicMock) -> None:
        """A 200 response with valid JSON is parsed into a dictionary."""
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.read.return_value = b'{"id": 25}'
        mock_urlopen.return_value.__enter__.return_value = mock_resp

        result = fetch_json("https://pokeapi.co/api/v2/pokemon/25")
        self.assertEqual(result, {"id": 25})

    @patch("main.urllib.request.urlopen")
    def test_fetch_json_non_200_returns_none(self, mock_urlopen: MagicMock) -> None:
        """Non-200 status codes yield None without raising."""
        mock_resp = MagicMock()
        mock_resp.status = 404
        mock_resp.read.return_value = b"Not Found"
        mock_urlopen.return_value.__enter__.return_value = mock_resp

        self.assertIsNone(fetch_json("https://pokeapi.co/api/v2/pokemon/99999"))

    @patch("main.urllib.request.urlopen")
    def test_fetch_json_url_error_returns_none(self, mock_urlopen: MagicMock) -> None:
        """Network errors are reported and mapped to None."""
        mock_urlopen.side_effect = urllib.error.URLError("connection reset")
        stderr = io.StringIO()
        with redirect_stderr(stderr):
            result = fetch_json("https://pokeapi.co/api/v2/pokemon/25")
        self.assertIsNone(result)
        self.assertIn("Error fetching data from", stderr.getvalue())

    @patch("main.urllib.request.urlopen")
    def test_fetch_json_malformed_payload_returns_none(
        self, mock_urlopen: MagicMock
    ) -> None:
        """Invalid JSON payloads are treated as failures."""
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.read.return_value = b"{broken json"
        mock_urlopen.return_value.__enter__.return_value = mock_resp

        self.assertIsNone(fetch_json("https://pokeapi.co/api/v2/pokemon/25"))


class TestEvolutionChainEdgeCases(unittest.TestCase):
    """Tests for evolution chain lookup failure modes."""

    @patch("main.fetch_json")
    def test_species_fetch_failure(self, mock_fetch: MagicMock) -> None:
        """Species lookup failures yield an empty chain."""
        mock_fetch.return_value = None
        self.assertEqual(fetch_evolution_chain("https://x/species/1"), [])

    @patch("main.fetch_json")
    def test_missing_evolution_chain_key(self, mock_fetch: MagicMock) -> None:
        """Payloads without an evolution_chain reference yield nothing."""
        mock_fetch.return_value = {"name": "pikachu"}
        self.assertEqual(fetch_evolution_chain("https://x/species/1"), [])

    @patch("main.fetch_json")
    def test_missing_evolution_chain_url(self, mock_fetch: MagicMock) -> None:
        """An empty chain URL reference yields an empty chain."""
        mock_fetch.return_value = {"evolution_chain": {"url": ""}}
        self.assertEqual(fetch_evolution_chain("https://x/species/1"), [])

    @patch("main.fetch_json")
    def test_evo_payload_without_chain(self, mock_fetch: MagicMock) -> None:
        """Evolution payloads lacking the chain node yield nothing."""
        mock_fetch.side_effect = [
            {"evolution_chain": {"url": "https://x/evolution-chain/10"}},
            {"id": 10},
        ]
        self.assertEqual(fetch_evolution_chain("https://x/species/1"), [])


class TestCardFormatting(unittest.TestCase):
    """Tests for stat card formatting fallbacks."""

    def test_card_without_evolutions_shows_na(self) -> None:
        """Missing evolution chains render N/A in the card."""
        card = format_pokemon_card(
            {"id": 132, "name": "ditto", "height": 3, "weight": 40}, []
        )
        self.assertIn("Evolutions : N/A", card)
        self.assertIn("#132 DITTO", card)


class TestCli(unittest.TestCase):
    """CLI-level tests covering main() flows via sys.argv."""

    def _run_cli(self, *args: str) -> Any:
        """Run main() with patched argv; capture streams and exit code."""
        stdout, stderr = io.StringIO(), io.StringIO()
        exit_code: Any = None
        argv = ["main.py"] + list(args)
        with redirect_stdout(stdout), redirect_stderr(stderr), patch("sys.argv", argv):
            try:
                main()
            except SystemExit as exc:
                exit_code = exc.code
        return stdout.getvalue(), stderr.getvalue(), exit_code

    def setUp(self) -> None:
        self.pokemon = {
            "id": 25,
            "name": "pikachu",
            "height": 4,
            "weight": 60,
            "types": [{"type": {"name": "electric"}}],
            "abilities": [{"ability": {"name": "static"}}],
            "stats": [{"stat": {"name": "hp"}, "base_stat": 35}],
            "sprites": {"front_default": "https://sprite/25.png"},
            "species": {"url": "https://pokeapi.co/api/v2/pokemon-species/25/"},
        }

    @patch("main.export_json")
    @patch("main.fetch_evolution_chain")
    @patch("main.fetch_pokemon_data")
    def test_cli_success_prints_card_and_exports(
        self,
        mock_data: MagicMock,
        mock_evo: MagicMock,
        mock_export: MagicMock,
    ) -> None:
        """A successful run prints the card and exports JSON."""
        mock_data.return_value = dict(self.pokemon)
        mock_evo.return_value = ["Pichu", "Pikachu"]
        mock_export.return_value = True
        stdout, _, code = self._run_cli("pikachu", "--json", "out.json")
        self.assertIsNone(code)
        self.assertIn("POKÉMON STAT CARD: #25 PIKACHU", stdout)
        self.assertIn("Pichu -> Pikachu", stdout)
        self.assertIn("Successfully exported data to out.json", stdout)
        mock_export.assert_called_once()

    @patch("main.fetch_pokemon_data")
    def test_cli_raw_mode_prints_json(self, mock_data: MagicMock) -> None:
        """--raw prints the untouched API payload."""
        mock_data.return_value = dict(self.pokemon)
        stdout, _, code = self._run_cli("pikachu", "--raw")
        self.assertIsNone(code)
        self.assertIn('"id": 25', stdout)
        self.assertNotIn("STAT CARD", stdout)

    @patch("main.fetch_pokemon_data")
    def test_cli_unknown_pokemon_exits_one(self, mock_data: MagicMock) -> None:
        """Unknown Pokémon exit 1 with a hint on stderr."""
        mock_data.return_value = None
        _, stderr, code = self._run_cli("missingmon")
        self.assertEqual(code, 1)
        self.assertIn("Could not find Pokémon 'missingmon'", stderr)


if __name__ == "__main__":
    unittest.main()
