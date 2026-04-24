---
name: transcript-validator
description: Validate that a submitted video is a legitimate cut from an original video by comparing transcripts. Use when verifying video submissions for the Colosseum hackathon, when checking if video B's audio is contained in video A's audio, or when needing to detect if a video uses audio from another source without permission.
---

# Transcript Validator Skill

Validates that a submitted video (Video B) is a legitimate cut from an original video (Video A) by comparing their transcripts.

## When to use this skill

Use this skill when:
- A user submits a video for a hackathon or contest and you need to verify it's actually a cut from the original
- Checking if video B's audio/content is contained in video A
- Validating video submissions where the audio should match between original and submitted versions
- Detecting potential audio-only theft (using audio without the corresponding video)

## How it works

The validation process:
1. Fetch transcripts from both YouTube videos
2. Normalize the text (lowercase, remove punctuation)
3. Calculate similarity score between transcripts
4. Return pass/fail based on threshold

## Dependencies

Install required packages:
```bash
pip install youtube-transcript-api numpy
```

Or add to requirements.txt:
```
youtube-transcript-api>=0.6.0
numpy>=1.24.0
```

## Step-by-step validation

### Step 1: Extract Video ID from URL

```python
def extract_video_id(url: str) -> str:
    """Extract YouTube video ID from various URL formats."""
    import re

    patterns = [
        r'(?:youtube\.com/watch\?v=)([a-zA-Z0-9_-]{11})',
        r'(?:youtu\.be/)([a-zA-Z0-9_-]{11})',
        r'(?:youtube\.com/embed/)([a-zA-Z0-9_-]{11})',
    ]

    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)

    # If no pattern matches, assume input is already a video ID
    return url
```

### Step 2: Fetch Transcript

```python
from youtube_transcript_api import YouTubeTranscriptApi

def fetch_transcript(video_id: str) -> str:
    """Fetch transcript and return as plain text."""
    try:
        transcript = YouTubeTranscriptApi().fetch(video_id)

        # Join all text segments
        text = ' '.join([segment['text'] for segment in transcript])

        return text
    except Exception as e:
        print(f"Error fetching transcript: {e}")
        return None
```

### Step 3: Normalize Text

```python
import re

def normalize_text(text: str) -> str:
    """Normalize text for comparison."""
    if not text:
        return ""

    # Lowercase
    text = text.lower()

    # Remove punctuation except spaces
    text = re.sub(r'[^\w\s]', '', text)

    # Remove extra whitespace
    text = ' '.join(text.split())

    return text
```

### Step 4: Calculate Similarity

```python
def calculate_match_score(text_a: str, text_b: str) -> float:
    """
    Calculate how much of text_b is contained in text_a.
    Returns a score between 0.0 and 1.0.
    """
    if not text_a or not text_b:
        return 0.0

    # Normalize both texts
    norm_a = normalize_text(text_a)
    norm_b = normalize_text(text_b)

    if not norm_b:
        return 0.0

    # Method: Check if text_b is substring of text_a
    # and calculate the ratio
    if norm_b in norm_a:
        return 1.0

    # If not exact match, use word-level comparison
    words_a = set(norm_a.split())
    words_b = norm_b.split()

    if not words_b:
        return 0.0

    # Count matching words from text_b that appear in text_a
    matching_words = sum(1 for word in words_b if word in words_a)

    score = matching_words / len(words_b)

    return min(score, 1.0)
```

### Step 5: Validate

```python
def validate_transcript(
    video_a_url: str,
    video_b_url: str,
    threshold: float = 0.70
) -> dict:
    """
    Validate that Video B is a cut from Video A.

    Args:
        video_a_url: URL of original video
        video_b_url: URL of submitted video
        threshold: Minimum match score (default 0.70 = 70%)

    Returns:
        dict with validation result
    """
    # Extract video IDs
    video_a_id = extract_video_id(video_a_url)
    video_b_id = extract_video_id(video_b_url)

    # Fetch transcripts
    transcript_a = fetch_transcript(video_a_id)
    transcript_b = fetch_transcript(video_b_id)

    if not transcript_a or not transcript_b:
        return {
            "valid": False,
            "error": "Could not fetch transcript for one or both videos",
            "video_a_id": video_a_id,
            "video_b_id": video_b_id,
            "score": 0.0
        }

    # Calculate similarity
    score = calculate_match_score(transcript_a, transcript_b)

    # Determine if valid
    is_valid = score >= threshold

    return {
        "valid": is_valid,
        "video_a_id": video_a_id,
        "video_b_id": video_b_id,
        "score": round(score, 3),
        "threshold": threshold,
        "transcript_a_preview": transcript_a[:200] + "...",
        "transcript_b_preview": transcript_b[:200] + "..."
    }
```

## Usage Example

```python
result = validate_transcript(
    video_a_url="https://www.youtube.com/watch?v=ORIGINAL_VIDEO_ID",
    video_b_url="https://www.youtube.com/watch?v=SUBMITTED_VIDEO_ID",
    threshold=0.70  # 70% match required
)

print(f"Valid: {result['valid']}")
print(f"Score: {result['score']}%")

if result['valid']:
    print("✅ Video B appears to be a legitimate cut from Video A")
else:
    print(f"❌ Transcript mismatch: only {result['score']}% match")
```

## Threshold Guidelines

| Threshold | Use Case |
|------------|----------|
| 0.90 | Strict matching (same audio, minimal edits) |
| 0.70 | Default for hackathon (allows for transcription errors) |
| 0.50 | Lenient (significant edits or translations) |

**Recommendation for Colosseum:** Use 0.70 (70%) as threshold to account for:
- YouTube's automatic transcription errors
- Small edits or cuts in the submitted video
- Minor timing differences

## Error Handling

Common errors and solutions:

1. **"No transcripts available"**
   - Video may not have captions enabled
   - Solution: Use ASR (Automatic Speech Recognition) service

2. **"Transcript timing issues"**
   - Videos may have different durations
   - Solution: Compare only common time segments

3. **"Language mismatch"**
   - Videos in different languages
   - Solution: Not valid - return failure

## Output Structure

The skill returns this structure:

```python
{
    "valid": bool,           # Pass/fail
    "video_a_id": str,       # Original video ID
    "video_b_id": str,      # Submitted video ID
    "score": float,          # Match score (0.0 - 1.0)
    "threshold": float,      # Threshold used
    "error": str|None,      # Error message if any
}
```

## Integration Points

This skill validates ONLY the transcript portion. For full validation, combine with:

1. **Frame validation skill** - Compare screenshots at matching timestamps
2. **Channel verification skill** - Verify Video B was posted on creator's channel

The full validation pipeline:
1. Run TranscriptValidator (this skill)
2. If passes → Run FrameValidator
3. If passes → Run ChannelVerifier
4. If all pass → Mark as valid for scoring