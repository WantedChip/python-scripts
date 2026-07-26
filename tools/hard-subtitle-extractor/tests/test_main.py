import os
import tempfile
import unittest

from main import SubtitleExtractor, SubtitleItem


class TestHardSubtitleExtractor(unittest.TestCase):

    def test_subtitle_item_formatting(self) -> None:
        item = SubtitleItem(
            index=1, start_time=1.5, end_time=4.25, text="Hello Subtitle"
        )
        srt_text = item.to_srt_string()
        self.assertIn("1\n", srt_text)
        self.assertIn("00:00:01,500 --> 00:00:04,250", srt_text)
        self.assertIn("Hello Subtitle", srt_text)

    def test_deduplicate_and_reconstruct(self) -> None:
        extractor = SubtitleExtractor("fake.mp4", sample_interval=1.0, mock_mode=True)
        sampled = [
            (0.0, ""),
            (1.0, "First Subtitle"),
            (2.0, "First Subtitle"),
            (3.0, ""),
            (4.0, "Second Subtitle"),
            (5.0, ""),
        ]
        subtitles = extractor.deduplicate_and_reconstruct(sampled)
        self.assertEqual(len(subtitles), 2)

        self.assertEqual(subtitles[0].text, "First Subtitle")
        self.assertEqual(subtitles[0].start_time, 1.0)
        self.assertEqual(subtitles[0].end_time, 3.0)

        self.assertEqual(subtitles[1].text, "Second Subtitle")
        self.assertEqual(subtitles[1].start_time, 4.0)
        self.assertEqual(subtitles[1].end_time, 5.0)

    def test_save_srt(self) -> None:
        extractor = SubtitleExtractor("fake.mp4", mock_mode=True)
        subtitles = [
            SubtitleItem(1, 0.0, 2.0, "Test 1"),
            SubtitleItem(2, 2.5, 4.5, "Test 2"),
        ]
        with tempfile.TemporaryDirectory() as tmpdir:
            srt_path = os.path.join(tmpdir, "test.srt")
            extractor.save_srt(subtitles, srt_path)
            self.assertTrue(os.path.exists(srt_path))
            with open(srt_path, "r", encoding="utf-8") as f:
                content = f.read()
            self.assertIn("Test 1", content)
            self.assertIn("Test 2", content)


if __name__ == "__main__":
    unittest.main()
