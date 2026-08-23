"""Unit tests for the hard-subtitle-extractor tool."""

import importlib
import os
import sys
import tempfile
import types
import unittest
from typing import Any, List, Optional

import main as main_module
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

    def test_deduplicate_finalizes_open_subtitle_at_end(self) -> None:
        """A subtitle still open when sampling ends is closed automatically."""
        extractor = SubtitleExtractor("fake.mp4", sample_interval=1.0, mock_mode=True)
        subtitles = extractor.deduplicate_and_reconstruct(
            [(0.0, "Tail"), (1.0, "Tail")]
        )
        self.assertEqual(len(subtitles), 1)
        self.assertEqual(subtitles[0].text, "Tail")
        self.assertEqual(subtitles[0].end_time, 2.0)

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


class _FakeFrame:
    """Minimal video frame stand-in supporting ROI slicing."""

    def __init__(self, height: int = 100, width: int = 80) -> None:
        self.shape = (height, width, 3)

    def __getitem__(self, key: Any) -> List[List[int]]:
        """Return a nested-list pixel block for the requested ROI window."""
        rows, cols = key[0], key[1]
        h = max(rows.stop - rows.start, 1)
        w = max(cols.stop - cols.start, 1)
        return [[128] * w for _ in range(h)]


class _GrayPixels:
    """Grayscale buffer exposing the array interface for PIL.Image.fromarray."""

    def __init__(self, width: int = 8, height: int = 4) -> None:
        self.__array_interface__ = {
            "shape": (height, width),
            "typestr": "|u1",
            "data": bytes([128] * (width * height)),
            "version": 3,
        }


def _make_fake_pil() -> types.ModuleType:
    """Build a fake ``PIL`` package whose Image.fromarray is an identity."""
    pil_pkg = types.ModuleType("PIL")
    image_mod = types.ModuleType("PIL.Image")
    image_mod.fromarray = lambda obj: obj
    pil_pkg.Image = image_mod
    return pil_pkg


def _make_fake_cv2(
    frame_count: int = 6,
    fps: float = 2.0,
    opens: bool = True,
) -> types.ModuleType:
    """Build a fake ``cv2`` module driving a scripted capture pipeline."""
    fake = types.ModuleType("cv2")
    fake.COLOR_BGR2GRAY = 6
    fake.THRESH_BINARY = 0
    fake.CAP_PROP_FPS = 5
    remaining_frames = frame_count

    class _FakeCapture:
        """Scripted VideoCapture yielding fixed frames until exhausted."""

        def __init__(self, path: str) -> None:
            self.path = path

        def isOpened(self) -> bool:
            return opens

        def get(self, prop: int) -> float:
            return fps if prop == fake.CAP_PROP_FPS else 0.0

        def read(self):
            nonlocal_remaining[0] -= 1
            if nonlocal_remaining[0] < 0:
                return False, None
            return True, _FakeFrame()

        def release(self) -> None:
            pass

    nonlocal_remaining = [remaining_frames]
    fake.VideoCapture = _FakeCapture
    fake.cvtColor = lambda frame, code: _GrayPixels()
    fake.threshold = lambda gray, thresh, maxval, flag: (thresh, _GrayPixels())
    return fake


def _make_fake_pytesseract(
    texts: Optional[List[str]] = None,
    side_effect: Optional[Exception] = None,
) -> types.ModuleType:
    """Build a fake ``pytesseract`` module returning scripted OCR text."""
    fake = types.ModuleType("pytesseract")
    remaining = list(texts or [])

    def image_to_string(image: Any, config: str = "") -> str:
        del image, config
        if side_effect is not None:
            raise side_effect
        return remaining.pop(0) if remaining else ""

    fake.image_to_string = image_to_string
    return fake


class _FakeModuleContext:
    """Swaps optional-dependency modules and reloads main.py."""

    def __init__(
        self,
        cv2_module: Optional[types.ModuleType],
        pytesseract_module: Optional[types.ModuleType],
    ) -> None:
        self.saved = {
            name: sys.modules.get(name) for name in ("cv2", "pytesseract", "PIL")
        }
        self.cv2_module = cv2_module
        self.pytesseract_module = pytesseract_module

    def __enter__(self) -> types.ModuleType:
        sys.modules["cv2"] = self.cv2_module
        if self.pytesseract_module is None:
            # None in sys.modules makes ``import`` raise ImportError again,
            # exercising the guarded-import fallback in main.py.
            sys.modules["pytesseract"] = None
            sys.modules["PIL"] = None
        else:
            sys.modules["pytesseract"] = self.pytesseract_module
            sys.modules["PIL"] = _make_fake_pil()
        return importlib.reload(main_module)

    def __exit__(self, *exc_info: Any) -> None:
        for name, module in self.saved.items():
            if module is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = module
        importlib.reload(main_module)


class TestDependencyFallbacks(unittest.TestCase):
    """Tests for behaviour when optional dependencies are unavailable."""

    def test_missing_dependencies_forces_mock_mode(self) -> None:
        """Without cv2/pytesseract the extractor silently runs in mock mode."""
        with _FakeModuleContext(None, None) as mod:
            self.assertFalse(mod.CV2_AVAILABLE)
            self.assertFalse(mod.PYTESSERACT_AVAILABLE)
            extractor = mod.SubtitleExtractor("video.mp4")
            self.assertTrue(extractor.mock_mode)


class TestRealPipelineWithFakes(unittest.TestCase):
    """Exercises the real OCR pipeline using fake cv2/pytesseract modules."""

    def test_crop_roi_slices_expected_window(self) -> None:
        """ROI ratios are converted to pixel bounds before slicing."""
        with _FakeModuleContext(_make_fake_cv2(), _make_fake_pytesseract()) as mod:
            extractor = mod.SubtitleExtractor("video.mp4")
            cropped = extractor.crop_roi(_FakeFrame(height=100, width=80))
        self.assertEqual(len(cropped), 20)
        self.assertEqual(len(cropped[0]), 80)

    def test_crop_roi_none_frame_passthrough(self) -> None:
        """A None frame is returned unchanged instead of being sliced."""
        with _FakeModuleContext(_make_fake_cv2(), _make_fake_pytesseract()) as mod:
            extractor = mod.SubtitleExtractor("video.mp4")
            self.assertIsNone(extractor.crop_roi(None))

    def test_perform_ocr_cleans_text(self) -> None:
        """OCR output whitespace is normalized to single-space text."""
        fake_ocr = _make_fake_pytesseract(texts=["  HELLO\nWORLD \n"])
        with _FakeModuleContext(_make_fake_cv2(), fake_ocr) as mod:
            extractor = mod.SubtitleExtractor("video.mp4")
            text = extractor.perform_ocr([[1, 2]])
        self.assertEqual(text, "HELLO WORLD")

    def test_perform_ocr_runtime_error_returns_empty(self) -> None:
        """OCR failures degrade to empty text instead of crashing."""
        failing = _make_fake_pytesseract(side_effect=RuntimeError("ocr down"))
        with _FakeModuleContext(_make_fake_cv2(), failing) as mod:
            extractor = mod.SubtitleExtractor("video.mp4")
            self.assertEqual(extractor.perform_ocr([[1, 2]]), "")

    def test_process_video_samples_frames_and_builds_subtitles(self) -> None:
        """Frames are sampled every N seconds, OCR'd, and deduplicated."""
        fake_cv2 = _make_fake_cv2(fps=2.0)
        fake_ocr = _make_fake_pytesseract(texts=["  A\n", "A ", "B"])
        with _FakeModuleContext(fake_cv2, fake_ocr) as mod:
            extractor = mod.SubtitleExtractor("video.mp4", sample_interval=1.0)
            subtitles = extractor.process_video()

        self.assertEqual(len(subtitles), 2)
        self.assertEqual(subtitles[0].text, "A")
        self.assertEqual(subtitles[0].start_time, 0.0)
        self.assertEqual(subtitles[0].end_time, 2.0)
        self.assertEqual(subtitles[1].text, "B")
        self.assertEqual(subtitles[1].start_time, 2.0)

    def test_process_video_unopenable_file_raises(self) -> None:
        """An unopenable video surfaces as FileNotFoundError."""
        fake_cv2 = _make_fake_cv2(opens=False)
        with _FakeModuleContext(fake_cv2, _make_fake_pytesseract()) as mod:
            extractor = mod.SubtitleExtractor("missing.mp4")
            with self.assertRaises(FileNotFoundError):
                extractor.process_video()


class TestMainCLI(unittest.TestCase):
    """CLI entry point tests run in mock mode."""

    def test_main_mock_writes_srt_file(self) -> None:
        """The CLI extracts the fallback mock sequence and writes an SRT."""
        with tempfile.TemporaryDirectory() as tmpdir:
            out_path = os.path.join(tmpdir, "out.srt")
            code = main_module.main(
                ["--video", "clip.mp4", "--output", out_path, "--mock"]
            )
            self.assertEqual(code, 0)
            with open(out_path, "r", encoding="utf-8") as f:
                content = f.read()
        self.assertIn("Hello world", content)
        self.assertIn("-->", content)

    def test_build_parser_defaults(self) -> None:
        """Parser exposes video/output/interval/mock options with defaults."""
        parsed = main_module.build_parser().parse_args(["--video", "v.mp4"])
        self.assertEqual(parsed.video, "v.mp4")
        self.assertEqual(parsed.output, "output.srt")
        self.assertEqual(parsed.interval, 0.5)
        self.assertFalse(parsed.mock)


if __name__ == "__main__":
    unittest.main()
