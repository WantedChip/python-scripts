# Video Slide Extractor

Automatically detect slide transitions in lectures, webinars, or presentation videos and export unique slides as images with timestamps.

## Features
- **Frame Difference Calculation**: Uses frame comparisons to identify major visual transitions (slide changes).
- **Deduplication Thresholding**: Configurable visual difference sensitivity threshold to prevent exporting identical consecutive slides.
- **Timestamped Filenames**: Outputs slide images tagged with exact video timestamps (`slide_001_00_01_25.png`).
- **Mock Execution Mode**: Works seamlessly in test environments without OpenCV binaries.

## Requirements
```bash
pip install -r requirements.txt
```

## Usage
```bash
python main.py --video lecture.mp4 --output-dir slides_out --threshold 0.15 --interval 1.0
```

Mock run:
```bash
python main.py --video mock_lecture.mp4 --output-dir mock_slides --mock
```

## Running Tests
```bash
python -m unittest discover tests
```
