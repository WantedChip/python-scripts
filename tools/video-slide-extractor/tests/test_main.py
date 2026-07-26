import os
import tempfile
import unittest

from main import VideoSlideExtractor


class TestVideoSlideExtractor(unittest.TestCase):

    def test_format_timestamp(self) -> None:
        extractor = VideoSlideExtractor("dummy.mp4", mock_mode=True)
        formatted = extractor.format_timestamp(3665.0)
        self.assertEqual(formatted, "01_01_05")

    def test_mock_slide_extraction(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            extractor = VideoSlideExtractor(
                video_path="dummy.mp4", output_dir=tmpdir, threshold=0.2, mock_mode=True
            )
            mock_data = [
                (0.0, 1.0, "Slide 1"),
                (1.0, 0.05, "Slide 1"),
                (2.0, 0.35, "Slide 2"),
            ]
            slides = extractor.extract_slides(mock_frames=mock_data)
            self.assertEqual(len(slides), 2)
            self.assertEqual(slides[0].slide_index, 1)
            self.assertEqual(slides[1].slide_index, 2)
            p0 = os.path.join(tmpdir, slides[0].image_filename)
            p1 = os.path.join(tmpdir, slides[1].image_filename)
            self.assertTrue(os.path.exists(p0))
            self.assertTrue(os.path.exists(p1))


if __name__ == "__main__":
    unittest.main()
