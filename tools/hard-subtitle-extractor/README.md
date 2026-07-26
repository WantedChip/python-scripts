# Hard Subtitle Extractor

Extract burned-in subtitles from videos using Optical Character Recognition (OCR), deduplicate consecutive frames, reconstruct timing, and export standard `.srt` subtitle files.

## Features
- **ROI Configuration**: Crop to the bottom region (or custom region) of the video where subtitles appear.
- **Frame Deduplication**: Merges consecutive identical OCR readings into single subtitle duration blocks.
- **Fallback / Mock Mode**: Automatically operates in mock mode if `opencv-python` or `pytesseract` are not installed, facilitating unit testing and dry runs.
- **SRT Export**: Exports output in standard SubRip format (`HH:MM:SS,mmm`).

## Requirements
```bash
pip install -r requirements.txt
```
*Note: Requires Tesseract OCR binary installed on the system if running in live OCR mode.*

## Usage
```bash
python main.py --video path/to/video.mp4 --output output.srt --interval 0.5
```

For mock testing:
```bash
python main.py --video sample.mp4 --output mock_output.srt --mock
```

## Running Tests
```bash
python -m unittest discover tests
```
