import os
import tempfile
import unittest

from main import (
    PropertyListing,
    export_csv,
    export_json,
    filter_listings,
    normalize_price,
    parse_listings,
    tag_features,
)


class TestRealEstateListingScraper(unittest.TestCase):

    def test_normalize_price(self):
        val, curr, ltype = normalize_price("$1,250,000")
        self.assertEqual(val, 1250000.0)
        self.assertEqual(curr, "USD")
        self.assertEqual(ltype, "sale")

        val, curr, ltype = normalize_price("$3,500/mo")
        self.assertEqual(val, 3500.0)
        self.assertEqual(ltype, "rent")

        val, curr, ltype = normalize_price("EUR 450k")
        self.assertEqual(val, 450000.0)
        self.assertEqual(curr, "EUR")
        self.assertEqual(ltype, "sale")

    def test_tag_features(self):
        tags = tag_features(
            "Luxury villa with a swimming pool, private garage, and balcony"
        )
        self.assertIn("pool", tags)
        self.assertIn("garage", tags)
        self.assertIn("balcony", tags)

    def test_parse_json_listings(self):
        json_data = """
        [
            {
                "@type": "SingleFamilyResidence",
                "name": "Sunset Modern Villa",
                "price": "$2,500,000",
                "address": {
                    "streetAddress": "123 Ocean Drive",
                    "addressLocality": "Miami",
                },
                "numberOfBedrooms": 4,
                "numberOfBathroomsTotal": 3.5,
                "floorSize": {"value": 3200},
                "description": "Beautiful waterfront house with pool and garage"
            }
        ]
        """
        listings = parse_listings(json_data)
        self.assertEqual(len(listings), 1)
        item = listings[0]
        self.assertEqual(item.title, "Sunset Modern Villa")
        self.assertEqual(item.price, 2500000.0)
        self.assertEqual(item.bedrooms, 4.0)
        self.assertIn("pool", item.features)
        self.assertIn("waterfront", item.features)

    def test_filter_listings(self):
        p1 = PropertyListing("P1", price=500000, bedrooms=2, features=["pool"])
        p2 = PropertyListing("P2", price=1200000, bedrooms=4, features=["garage"])
        listings = [p1, p2]

        filtered = filter_listings(listings, min_price=600000)
        self.assertEqual(len(filtered), 1)
        self.assertEqual(filtered[0].title, "P2")

        filtered_feat = filter_listings(listings, feature="pool")
        self.assertEqual(len(filtered_feat), 1)
        self.assertEqual(filtered_feat[0].title, "P1")

    def test_exports(self):
        p = PropertyListing("Test Home", price=300000, bedrooms=3, features=["garage"])
        with tempfile.TemporaryDirectory() as tmpdir:
            csv_path = os.path.join(tmpdir, "out.csv")
            json_path = os.path.join(tmpdir, "out.json")

            export_csv([p], csv_path)
            self.assertTrue(os.path.exists(csv_path))

            export_json([p], json_path)
            self.assertTrue(os.path.exists(json_path))


if __name__ == "__main__":
    unittest.main()
