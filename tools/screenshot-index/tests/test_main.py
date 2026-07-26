import unittest

from main import ScreenshotIndexer


class TestScreenshotIndexer(unittest.TestCase):

    def setUp(self) -> None:
        self.indexer = ScreenshotIndexer(db_path=":memory:")

    def test_add_and_search_by_keyword(self) -> None:
        self.indexer.add_screenshot(
            filepath="img1.png",
            app_name="VSCode",
            topic="Coding",
            created_at="2026-07-20",
            mock_text="def connect_to_database(): return True",
        )
        self.indexer.add_screenshot(
            filepath="img2.png",
            app_name="Slack",
            topic="Chat",
            created_at="2026-07-21",
            mock_text="Hey team, meeting starts at 3 PM",
        )

        results = self.indexer.search(keyword="database")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].app_name, "VSCode")
        self.assertIn("connect_to_database", results[0].text_content)

    def test_search_by_app_and_date_range(self) -> None:
        self.indexer.add_screenshot(
            filepath="img1.png",
            app_name="Chrome",
            created_at="2026-07-10",
            mock_text="Python documentation",
        )
        self.indexer.add_screenshot(
            filepath="img2.png",
            app_name="Chrome",
            created_at="2026-07-22",
            mock_text="GitHub repository view",
        )

        results = self.indexer.search(
            app_name="Chrome",
            start_date="2026-07-15",
            end_date="2026-07-25",
        )
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].created_at, "2026-07-22")


if __name__ == "__main__":
    unittest.main()
