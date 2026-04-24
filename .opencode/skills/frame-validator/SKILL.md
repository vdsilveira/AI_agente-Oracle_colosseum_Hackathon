---
name: frame-validator
description: Validate that video frames match between original and submitted videos using image similarity. Use when verifying视频 B is using the same visual content as video A, detecting if someone is using just the audio without the video, or comparing screenshots at matching timestamps.
---

# Frame Validator Skill

Validates that a submitted video (Video B) visually matches an original video (Video A) by comparing frames at multiple timestamps.

## When to use this skill

Use this skill when:
- Verifying that Video B contains the same visual content as Video A
- Detecting audio-only theft (using audio without corresponding video)
- Comparing screenshots at matching timestamps between videos
- Running the second stage of video validation after transcript validation passes

## How it works

The validation process:
1. Find timestamps where transcripts match
2. Extract frames from both videos at those timestamps
3. Compare frames using SSIM (Structural Similarity Index)
4. Return pass/fail based on threshold

## Dependencies

Install required packages:
```bash
pip install opencv-python numpy scikit-image yt-dlp
```

Or add to requirements.txt:
```
opencv-python>=4.8.0
numpy>=1.24.0
scikit-image>=0.21.0
yt-dlp>=2023.12.0
```

## Installation Requirements

This skill requires **FFmpeg** to be installed on the system:
- **macOS:** `brew install ffmpeg`
- **Ubuntu/Debian:** `sudo apt install ffmpeg`
- **Windows:** Download from ffmpeg.org or use chocolatey

## Step-by-step validation

### Step 1: Install yt-dlp and extract video

```python
import subprocess
import os

def download_video_frame(video_id: str, timestamp: float, output_path: str) -> str:
    """
    Download a frame from YouTube video at specific timestamp.

    Args:
        video_id: YouTube video ID
        timestamp: Time in seconds
        output_path: Where to save the frame

    Returns:
        Path to saved frame or None on failure
    """
    url = f"https://www.youtube.com/watch?v={video_id}"

    # Use yt-dlp to extract frame at timestamp
    cmd = [
        "yt-dlp",
        "--download-frames", "1",
        "-ss", str(timestamp),
        "-frames:v", "1",
        "-o", output_path,
        url
    ]

    try:
        subprocess.run(cmd, check=True, capture_output=True)
        return output_path if os.path.exists(output_path) else None
    except Exception as e:
        print(f"Error downloading frame: {e}")
        return None
```

**Alternative: Use pytube3 for simpler extraction**

```python
from pytube import YouTube

def get_frame_pytube(video_id: str, timestamp: int) -> str:
    """Download frame using pytube."""
    url = f"https://www.youtube.com/watch?v={video_id}"
    yt = YouTube(url)

    # Get the first stream and download to temp
    video = yt.streams.first()
    temp_file = video.download(filename=f"temp_{video_id}")

    # Use cv2 to extract frame
    import cv2
    cap = cv2.VideoCapture(temp_file)
    cap.set(cv2.CAP_PROP_POS_MSEC, timestamp * 1000)
    ret, frame = cap.read()

    if ret:
        cv2.imwrite(f"frame_{video_id}_{timestamp}.jpg", frame)

    cap.release()
    os.remove(temp_file)

    return frame if ret else None
```

### Step 2: Compare frames with SSIM

```python
import cv2
import numpy as np
from skimage.metrics import structural_similarity as ssim

def compare_frames(frame_a: np.ndarray, frame_b: np.ndarray) -> float:
    """
    Compare two frames using SSIM.

    Args:
        frame_a: First frame (numpy array from cv2)
        frame_b: Second frame

    Returns:
        SSIM score between 0.0 and 1.0
    """
    # Convert to grayscale if needed
    if len(frame_a.shape) == 3:
        gray_a = cv2.cvtColor(frame_a, cv2.COLOR_BGR2GRAY)
    else:
        gray_a = frame_a

    if len(frame_b.shape) == 3:
        gray_b = cv2.cvtColor(frame_b, cv2.COLOR_BGR2GRAY)
    else:
        gray_b = frame_b

    # Resize to match
    if gray_a.shape != gray_b.shape:
        gray_b = cv2.resize(gray_b, (gray_a.shape[1], gray_a.shape[0]))

    # Calculate SSIM
    score = ssim(gray_a, gray_b)

    return float(score)
```

**Alternative: Simple pixel comparison**

```python
def simple_frame_compare(frame_a: np.ndarray, frame_b: np.ndarray) -> float:
    """Simple frame comparison using normalized difference."""
    if frame_a.shape != frame_b.shape:
        frame_b = cv2.resize(frame_b, (frame_a.shape[1], frame_a.shape[0]))

    # Calculate similarity
    diff = np.abs(frame_a.astype(float) - frame_b.astype(float))
    similarity = 1.0 - (np.mean(diff) / 255.0)

    return similarity
```

### Step 3: Find matching timestamps

```python
def find_matching_timestamps(
    transcript_a: list,
    transcript_b: list,
    n_points: int = 5
) -> list:
    """
    Find timestamps where transcript segments match.

    Args:
        transcript_a: Full transcript with timestamps
        transcript_b: Submitted video transcript
        n_points: Number of timestamps to return

    Returns:
        List of (timestamp_a, timestamp_b) tuples
    """
    # Normalize and find matching text segments
    from difflib import SequenceMatcher

    matches = []

    for seg_b in transcript_b:
        text_b = seg_b['text'].lower().strip()
        if len(text_b) < 10:  # Skip very short segments
            continue

        best_match = None
        best_ratio = 0

        for seg_a in transcript_a:
            text_a = seg_a['text'].lower().strip()
            ratio = SequenceMatcher(None, text_a, text_b).ratio()

            if ratio > best_ratio and ratio > 0.8:
                best_ratio = ratio
                best_match = (seg_a['start'], seg_b['start'])

        if best_match:
            matches.append(best_match)

        if len(matches) >= n_points:
            break

    return matches[:n_points]
```

### Step 4: Full validation

```python
import json
import os
import tempfile

def validate_frames(
    video_a_id: str,
    video_b_id: str,
    matched_timestamps: list = None,
    threshold: float = 0.70,
    min_matches: int = 3,
    total_samples: int = 5
) -> dict:
    """
    Validate that Video B's frames match Video A's frames.

    Args:
        video_a_id: Original video ID
        video_b_id: Submitted video ID
        matched_timestamps: List of timestamp pairs (optional)
        threshold: Minimum SSIM score per frame
        min_matches: Minimum frames that must match
        total_samples: Total frames to compare

    Returns:
        Validation result dictionary
    """
    # If no timestamps provided, use default points
    if not matched_timestamps:
        # Use 5 evenly distributed timestamps
        matched_timestamps = [(i * 10, i * 10) for i in range(1, total_samples + 1)]

    results = []
    temp_files = []

    try:
        for i, (time_a, time_b) in enumerate(matched_timestamps):
            # Create temp files
            temp_dir = tempfile.mkdtemp()

            frame_a_path = os.path.join(temp_dir, f"frame_a_{i}.jpg")
            frame_b_path = os.path.join(temp_dir, f"frame_b_{i}.jpg")

            # Download frames (pseudo-code - implement with yt-dlp)
            frame_a = download_video_frame(video_a_id, time_a, frame_a_path)
            frame_b = download_video_frame(video_b_id, time_b, frame_b_path)

            if frame_a and frame_b:
                # Read with cv2
                img_a = cv2.imread(frame_a)
                img_b = cv2.imread(frame_b)

                if img_a is not None and img_b is not None:
                    score = compare_frames(img_a, img_b)
                    results.append({
                        "timestamp_a": time_a,
                        "timestamp_b": time_b,
                        "score": score,
                        "passed": score >= threshold
                    })

            temp_files.extend([frame_a_path, frame_b_path])

        # Calculate overall result
        passed_count = sum(1 for r in results if r['passed'])

        is_valid = passed_count >= min_matches

        avg_score = sum(r['score'] for r in results) / len(results) if results else 0.0

        return {
            "valid": is_valid,
            "video_a_id": video_a_id,
            "video_b_id": video_b_id,
            "avg_ssim": round(avg_score, 3),
            "passed_count": passed_count,
            "total_samples": len(results),
            "min_matches_required": min_matches,
            "frame_results": results
        }

    finally:
        # Cleanup temp files
        for f in temp_files:
            if os.path.exists(f):
                os.remove(f)
```

## Usage Example

```python
result = validate_frames(
    video_a_id="ORIGINAL_VIDEO_ID",
    video_b_id="SUBMITTED_VIDEO_ID",
    matched_timestamps=[
        (15.5, 15.5),  # First matching segment
        (45.2, 30.1),  # Second matching segment
        (90.0, 60.0), # Third matching segment
        (120.5, 90.2),
        (150.0, 120.0)
    ],
    threshold=0.70,      # 70% SSIM per frame
    min_matches=3,       # At least 3 of 5 must pass
    total_samples=5
)

print(f"Valid: {result['valid']}")
print(f"Average SSIM: {result['avg_ssim']}%")
print(f"Passed: {result['passed_count']}/{result['total_samples']}")

if result['valid']:
    print("✅ Video B visually matches Video A")
else:
    print(f"❌ Frame mismatch: only {result['passed_count']} frames similar")
```

## Threshold Guidelines

| Threshold | Use Case |
|------------|----------|
| 0.90 | Near-identical frames |
| 0.70 | Default (allows for minor compression differences) |
| 0.50 | Lenient (significant edits or different sources) |

**Recommendation for Colosseum:** Use 0.70 threshold with 3/5 matches.

## SSIM vs Other Methods

| Method | Pros | Cons |
|--------|------|------|
| **SSIM** | Perceptual similarity, robust | Slower |
| Pixel diff | Fast, simple | Sensitive to brightness |
| Histogram | Scale invariant | Color-only |
| Feature match | Rotation invariant | More complex |

## Error Handling

1. **"FFmpeg not found"**
   - Install FFmpeg system-wide
   - Or add to PATH

2. **"No matching timestamps"**
   - Return failure - no reference points
   - Suggest running transcript validation first

3. **"Video unavailable"**
   - Video may be private or deleted
   - Handle gracefully, return error

## Output Structure

```python
{
    "valid": bool,
    "video_a_id": str,
    "video_b_id": str,
    "avg_ssim": float,           # Average SSIM score
    "passed_count": int,        # Frames above threshold
    "total_samples": int,        # Total frames compared
    "min_matches_required": int, # Minimum needed
    "frame_results": [
        {
            "timestamp_a": float,
            "timestamp_b": float,
            "score": float,
            "passed": bool
        },
        ...
    ]
}
```

## Integration

Frame validation is the second stage after transcript validation:

1. **TranscriptValidator** (first) - Verify audio similarity
2. **FrameValidator** (second) - Verify visual similarity
3. **ChannelVerifier** (third) - Verify video ownership

Run both validations for complete verification.