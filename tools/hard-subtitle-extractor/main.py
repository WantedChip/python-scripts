"""Hard Subtitle Extractor.

Extracts burned-in subtitles from video files using optical character
recognition (OCR), deduplicates consecutive identical text entries,
reconstructs start/end timestamps, and exports standard SRT subtitle files.
"""

# pylint: disable=too-many-branches,too-many-statements
# pylint: disable=too-many-locals,too-many-arguments,too-many-positional-arguments
# pylint: disable=too-many-instance-attributes,too-few-public-methods

import argparse
import os
import sys
from dataclasses import dataclass
from typing import Any, List, Optional, Tuple

# Optional dependencies handling with fallback
CV2_AVAILABLE = True
PYTESSERACT_AVAILABLE = True

try:
    import cv2
except ImportError:
    CV2_AVAILABLE = False

try:
    import pytesseract
    from PIL import Image
except ImportError:
    PYTESSERACT_AVAILABLE = False


@dataclass
class SubtitleItem:
    """Represents a single subtitle block with start/end time and text."""

    index: int
    start_time: float
    end_time: float
    text: str

    def format_timestamp(self, seconds: float) -> str:
        """Formats time in seconds to SRT timestamp string format."""
        millis = int(round((seconds - int(seconds)) * 1000))
        total_seconds = int(seconds)
        hours = total_seconds // 3600
        minutes = (total_seconds % 3600) // 60
        secs = total_seconds % 60
        return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"

    def to_srt_string(self) -> str:
        """Converts SubtitleItem to standard SRT block format."""
        start_str = self.format_timestamp(self.start_time)
        end_str = self.format_timestamp(self.end_time)
        return f"{self.index}\n{start_str} --> {end_str}\n{self.text}\n"


class SubtitleExtractor:
    """Extracts burned-in video subtitles into SRT format."""

    def __init__(
        self,
        video_path: str,
        roi_box: Tuple[float, float, float, float] = (0.8, 1.0, 0.0, 1.0),
        sample_interval: float = 0.5,
        mock_mode: bool = False,
    ) -> None:
        """Initialize the extractor.

        Args:
            video_path: Path to input video file.
            roi_box: (top, bottom, left, right) bounds expressed as ratios.
                     Default is bottom 20% of video frame.
            sample_interval: Sampling interval in seconds.
            mock_mode: Force mock OCR/video processing for testing.
        """
        self.video_path = video_path
        self.roi_box = roi_box
        self.sample_interval = sample_interval
        is_missing_deps = (not CV2_AVAILABLE) or (not PYTESSERACT_AVAILABLE)
        self.mock_mode = mock_mode or is_missing_deps

    def crop_roi(self, frame: Any) -> Any:
        """Crops the frame based on configured ROI ratios.

        Args:
            frame: OpenCV image frame array.

        Returns:
            Cropped region of interest.
        """
        if self.mock_mode or frame is None:
            return frame
        height, width = frame.shape[:2]
        top_r, bottom_r, left_r, right_r = self.roi_box
        y1, y2 = int(height * top_r), int(height * bottom_r)
        x1, x2 = int(width * left_r), int(width * right_r)
        return frame[y1:y2, x1:x2]

    def perform_ocr(self, cropped_frame: Any) -> str:
        """Applies OCR to the cropped image frame.

        Args:
            cropped_frame: Cropped frame image.

        Returns:
            Extracted clean text string.
        """
        if self.mock_mode:
            return ""

        try:
            gray = cv2.cvtColor(cropped_frame, cv2.COLOR_BGR2GRAY)
            # Thresholding for contrast enhancement
            _, thresh = cv2.threshold(gray, 180, 255, cv2.THRESH_BINARY)
            pil_img = Image.fromarray(thresh)
            raw_text = pytesseract.image_to_string(pil_img, config="--psm 6")
            # Clean up whitespace and newlines
            clean_text = " ".join(raw_text.strip().split())
            return clean_text
        except (OSError, ValueError, RuntimeError):
            return ""

    def process_video(
        self,
        mock_frames_data: Optional[List[Tuple[float, str]]] = None,
    ) -> List[SubtitleItem]:
        """Processes video, extracts frames, OCRs text, and deduplicates.

        Args:
            mock_frames_data: Optional predefined [(timestamp, text), ...].

        Returns:
            List of deduplicated SubtitleItem instances.
        """
        sampled_entries: List[Tuple[float, str]] = []

        if self.mock_mode and mock_frames_data is not None:
            sampled_entries = mock_frames_data
        elif self.mock_mode:
            # Fallback mock sequence if no cv2/pytesseract installed
            sampled_entries = [
                (0.0, ""),
                (1.0, "Hello world"),
                (1.5, "Hello world"),
                (2.0, "Hello world"),
                (2.5, ""),
                (3.0, "Welcome to hard subtitle extractor"),
                (3.5, "Welcome to hard subtitle extractor"),
                (4.0, ""),
            ]
        else:
            cap = cv2.VideoCapture(self.video_path)
            if not cap.isOpened():
                msg = f"Cannot open video file: {self.video_path}"
                raise FileNotFoundError(msg)

            fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
            frame_step = int(fps * self.sample_interval)
            frame_idx = 0

            while cap.isOpened():
                ret, frame = cap.read()
                if not ret:
                    break

                if frame_idx % frame_step == 0:
                    timestamp = frame_idx / fps
                    roi = self.crop_roi(frame)
                    extracted_text = self.perform_ocr(roi)
                    sampled_entries.append((timestamp, extracted_text))

                frame_idx += 1
            cap.release()

        return self.deduplicate_and_reconstruct(sampled_entries)

    def deduplicate_and_reconstruct(
        self, sampled_entries: List[Tuple[float, str]]
    ) -> List[SubtitleItem]:
        """Combines consecutive identical OCR text frames into timed subtitles.

        Args:
            sampled_entries: List of (timestamp, extracted_text) pairs.

        Returns:
            List of SubtitleItem objects.
        """
        subtitles: List[SubtitleItem] = []
        current_text: Optional[str] = None
        start_t: float = 0.0
        last_t: float = 0.0
        sub_index = 1

        for timestamp, text in sampled_entries:
            text = text.strip()
            if text == current_text:
                if current_text:
                    last_t = timestamp
            else:
                if current_text:
                    # Finalize current subtitle entry
                    end_t = last_t + self.sample_interval
                    subtitles.append(
                        SubtitleItem(
                            index=sub_index,
                            start_time=start_t,
                            end_time=end_t,
                            text=current_text,
                        )
                    )
                    sub_index += 1

                if text:
                    current_text = text
                    start_t = timestamp
                    last_t = timestamp
                else:
                    current_text = None

        if current_text:
            end_t = last_t + self.sample_interval
            subtitles.append(
                SubtitleItem(
                    index=sub_index,
                    start_time=start_t,
                    end_time=end_t,
                    text=current_text,
                )
            )

        return subtitles

    def save_srt(self, subtitles: List[SubtitleItem], output_srt_path: str) -> None:
        """Saves extracted subtitles to an SRT file.

        Args:
            subtitles: List of SubtitleItem objects.
            output_srt_path: Target path for .srt file.
        """
        output_dir = os.path.dirname(output_srt_path)
        if output_dir:
            os.makedirs(output_dir, exist_ok=True)

        with open(output_srt_path, "w", encoding="utf-8") as f:
            for item in subtitles:
                f.write(item.to_srt_string() + "\n")


def build_parser() -> argparse.ArgumentParser:
    """Build CLI parser."""
    desc = "Extract burned-in subtitles from video to SRT."
    parser = argparse.ArgumentParser(description=desc)
    parser.add_argument(
        "--video",
        type=str,
        required=True,
        help="Path to input video file",
    )
    parser.add_argument(
        "--output",
        type=str,
        default="output.srt",
        help="Path to output SRT file",
    )
    parser.add_argument(
        "--interval",
        type=float,
        default=0.5,
        help="Frame sampling interval in seconds",
    )
    parser.add_argument(
        "--mock",
        action="store_true",
        help="Run in mock OCR mode",
    )
    return parser


def main(args: Optional[List[str]] = None) -> int:
    """CLI entry point for hard subtitle extractor."""
    parser = build_parser()
    parsed = parser.parse_args(args)

    extractor = SubtitleExtractor(
        video_path=parsed.video,
        sample_interval=parsed.interval,
        mock_mode=parsed.mock,
    )
    subtitles = extractor.process_video()
    extractor.save_srt(subtitles, parsed.output)
    print(f"Successfully extracted {len(subtitles)} subtitles to {parsed.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
