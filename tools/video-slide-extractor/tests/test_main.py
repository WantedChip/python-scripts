"""Tests for the Video Slide Extractor tool."""

import contextlib
import io
import os
import runpy
import sys
import tempfile
import unittest
from pathlib import Path
from typing import List, Optional, Tuple
from unittest import mock

import main as vse_module
from main import VideoSlideExtractor, build_parser, main


class FakeDiffResult:
    """Stand-in for the array returned by ``cv2.absdiff``."""

    def __init__(self, mean_value: float) -> None:
        """Store the fixed mean pixel value to report."""
        self._mean_value = mean_value

    def mean(self) -> float:
        """Return the preconfigured mean."""
        return self._mean_value


class FakeFrame:
    """Video frame stand-in carrying its pairwise difference magnitude."""

    def __init__(self, diff_mean: float) -> None:
        """Store the absolute-difference mean against the previous frame."""
        self.diff_mean = diff_mean


class FakeCapture:
    """Stand-in for ``cv2.VideoCapture`` fed from a frame list."""

    def __init__(self, frames: List[FakeFrame], fps: float, opens: bool = True) -> None:
        """Store the scripted frame sequence and reported FPS."""
        self.frames = list(frames)
        self.fps = fps
        self.opens = opens
        self.released = False
        self.requested_path: Optional[str] = None

    def isOpened(self) -> bool:
        """Report whether the fake device opened."""
        return self.opens

    def get(self, prop: int) -> float:
        """Report the configured FPS value."""
        return self.fps

    def read(self) -> Tuple[bool, Optional[FakeFrame]]:
        """Pop the next scripted frame or signal end of stream."""
        if self.frames:
            return True, self.frames.pop(0)
        return False, None

    def release(self) -> None:
        """Mark the fake capture as released."""
        self.released = True


def build_fake_cv2(capture: FakeCapture) -> mock.Mock:
    """Create a ``cv2`` module replacement wired to ``capture``."""
    fake = mock.Mock()
    fake.COLOR_BGR2GRAY = 6
    fake.CAP_PROP_FPS = 5

    def fake_video_capture(path: str) -> FakeCapture:
        """Return the scripted capture, recording the requested path."""
        capture.requested_path = path
        return capture

    def fake_imwrite(path: str, frame: FakeFrame) -> bool:
        """Pretend to encode ``frame`` and write it to ``path``."""
        with open(path, "wb") as handle:
            handle.write(b"PNG:" + str(frame.diff_mean).encode())
        return True

    fake.VideoCapture.side_effect = fake_video_capture
    fake.cvtColor.side_effect = lambda frame, code: frame
    fake.resize.side_effect = lambda frame, size: frame
    fake.absdiff.side_effect = lambda a, b: FakeDiffResult(b.diff_mean)
    fake.imwrite.side_effect = fake_imwrite
    return fake


class TestHelpers(unittest.TestCase):
    """Tests for pure helper methods."""

    def test_format_timestamp_boundaries(self) -> None:
        """Timestamps format as zero-padded HH_MM_SS strings."""
        extractor = VideoSlideExtractor("dummy.mp4", mock_mode=True)
        self.assertEqual(extractor.format_timestamp(0.0), "00_00_00")
        self.assertEqual(extractor.format_timestamp(59.9), "00_00_59")
        self.assertEqual(extractor.format_timestamp(3665.0), "01_01_05")

    def test_calculate_frame_difference_shortcuts(self) -> None:
        """Missing frames or mock mode short-circuit to a zero score."""
        extractor = VideoSlideExtractor("dummy.mp4", mock_mode=True)
        frame = FakeFrame(120.0)
        self.assertEqual(extractor.calculate_frame_difference(None, frame), 0.0)
        self.assertEqual(extractor.calculate_frame_difference(frame, None), 0.0)
        self.assertEqual(
            extractor.calculate_frame_difference(FakeFrame(1.0), FakeFrame(2.0)), 0.0
        )

    def test_calculate_frame_difference_normalizes_by_255(self) -> None:
        """The difference score equals absdiff mean divided by 255."""
        capture = FakeCapture([], fps=30.0)
        with mock.patch.object(vse_module, "CV2_AVAILABLE", True):
            with mock.patch.object(
                vse_module, "cv2", build_fake_cv2(capture), create=True
            ):
                extractor = VideoSlideExtractor("dummy.mp4", mock_mode=False)
                score = extractor.calculate_frame_difference(
                    FakeFrame(0.0), FakeFrame(76.5)
                )
        self.assertAlmostEqual(score, 0.3)


class TestMockModeExtraction(unittest.TestCase):
    """Tests for mock-mode slide extraction."""

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

    def test_default_mock_frames_produce_three_slides(self) -> None:
        """Without explicit frames, the built-in demo sequence yields 3 slides."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            extractor = VideoSlideExtractor(
                video_path="demo.mp4", output_dir=tmp_dir, mock_mode=True
            )
            slides = extractor.extract_slides()
            self.assertEqual(len(slides), 3)
            self.assertEqual([s.slide_index for s in slides], [1, 2, 3])
            self.assertIn("Introduction", slides[0].ocr_text)
            self.assertTrue(
                all(
                    os.path.exists(os.path.join(tmp_dir, s.image_filename))
                    for s in slides
                )
            )

    def test_placeholder_file_written_without_pil(self) -> None:
        """When Pillow is unavailable a text placeholder image is written."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            extractor = VideoSlideExtractor(
                video_path="demo.mp4", output_dir=tmp_dir, mock_mode=True
            )
            with mock.patch.object(vse_module, "PIL_AVAILABLE", False):
                slides = extractor.extract_slides(mock_frames=[(0.0, 1.0, "Only")])
            placeholder = os.path.join(tmp_dir, slides[0].image_filename)
            with open(placeholder, encoding="utf-8") as handle:
                self.assertEqual(handle.read(), "mock image content")


class TestRealModeExtraction(unittest.TestCase):
    """Tests for the OpenCV processing path using a fake cv2 module."""

    def extract_with_fake_cv2(
        self,
        tmp_dir: str,
        frames: List[FakeFrame],
        fps: float = 10.0,
        sample_interval: float = 0.5,
        opens: bool = True,
    ):
        """Run extract_slides in real mode against a scripted capture."""
        capture = FakeCapture(frames, fps=fps, opens=opens)
        with mock.patch.object(vse_module, "CV2_AVAILABLE", True):
            with mock.patch.object(
                vse_module, "cv2", build_fake_cv2(capture), create=True
            ):
                extractor = VideoSlideExtractor(
                    video_path=os.path.join(tmp_dir, "lecture.mp4"),
                    output_dir=os.path.join(tmp_dir, "out"),
                    sample_interval=sample_interval,
                    mock_mode=False,
                )
                if not opens:
                    with self.assertRaises(FileNotFoundError) as ctx:
                        extractor.extract_slides()
                    self.assertIn("Unable to open video", str(ctx.exception))
                    return None, capture
                return extractor.extract_slides(), capture

    def test_unopenable_video_raises_filenotfound(self) -> None:
        """A video that cannot be opened raises FileNotFoundError."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            _, capture = self.extract_with_fake_cv2(tmp_dir, [], opens=False)
        self.assertEqual(capture.requested_path, os.path.join(tmp_dir, "lecture.mp4"))
        self.assertFalse(capture.released)

    def test_slide_detection_and_export(self) -> None:
        """Sampled frames above threshold become exported slide images."""
        frames = [FakeFrame(0.0)] * 15
        frames[5] = FakeFrame(13.0)
        frames[10] = FakeFrame(153.0)
        with tempfile.TemporaryDirectory() as tmp_dir:
            slides, capture = self.extract_with_fake_cv2(tmp_dir, frames)
            self.assertIsNotNone(slides)
            self.assertEqual(len(slides), 2)
            self.assertEqual(slides[0].formatted_time, "00_00_00")
            self.assertEqual(slides[1].formatted_time, "00_00_01")
            self.assertAlmostEqual(slides[1].difference_score, 0.6)
            for slide in slides:
                self.assertTrue(
                    os.path.exists(os.path.join(tmp_dir, "out", slide.image_filename))
                )
            self.assertTrue(capture.released)

    def test_missing_fps_defaults_to_thirty(self) -> None:
        """A capture reporting zero FPS falls back to 30 FPS sampling."""
        frames = [FakeFrame(0.0)] * 61
        with tempfile.TemporaryDirectory() as tmp_dir:
            slides, _ = self.extract_with_fake_cv2(
                tmp_dir, frames, fps=0.0, sample_interval=1.0
            )
            self.assertEqual(len(slides), 1)


class TestCommandLine(unittest.TestCase):
    """Tests for argument parsing and CLI orchestration."""

    def test_parser_defaults_and_flags(self) -> None:
        """Parser exposes documented defaults and a --mock switch."""
        parsed = build_parser().parse_args(["--video", "clip.mp4"])
        self.assertEqual(parsed.video, "clip.mp4")
        self.assertEqual(parsed.output_dir, "extracted_slides")
        self.assertAlmostEqual(parsed.threshold, 0.15)
        self.assertAlmostEqual(parsed.interval, 1.0)
        self.assertFalse(parsed.mock)
        parsed_mocked = build_parser().parse_args(["--video", "clip.mp4", "--mock"])
        self.assertTrue(parsed_mocked.mock)

    def test_main_extracts_in_mock_mode(self) -> None:
        """The CLI extracts slides into the requested output directory."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            buffer = io.StringIO()
            with contextlib.redirect_stdout(buffer):
                code = main(
                    ["--video", "lecture.mp4", "--mock", "--output-dir", tmp_dir]
                )
            self.assertEqual(code, 0)
            self.assertIn("Extracted 3 unique slides", buffer.getvalue())

    def test_dunder_main_exits_zero(self) -> None:
        """Executing main.py as a program exits cleanly in mock mode."""
        entry = str(Path(__file__).resolve().parents[1] / "main.py")
        with tempfile.TemporaryDirectory() as tmp_dir:
            argv = [
                entry,
                "--video",
                os.path.join(tmp_dir, "lecture.mp4"),
                "--mock",
                "--output-dir",
                os.path.join(tmp_dir, "slides"),
            ]
            with mock.patch.object(sys, "argv", argv):
                buffer = io.StringIO()
                with contextlib.redirect_stdout(buffer):
                    with self.assertRaises(SystemExit) as ctx:
                        runpy.run_path(entry, run_name="__main__")
            self.assertEqual(ctx.exception.code, 0)


if __name__ == "__main__":
    unittest.main()
