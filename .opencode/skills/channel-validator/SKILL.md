---
name: channel-validator
description: Verify that a YouTube video was posted on a channel owned by the creator. Use when validating video submissions for the Colosseum hackathon, checking if a video belongs to a specific channel, or verifying channel ownership for creator verification.
---

# Channel Validator Skill

Validates that a video was posted on a channel that belongs to the creator's registered channels.

## When to use this skill

Use this skill when:
- Verifying a submitted video belongs to one of the creator's channels
- Checking if video B was uploaded by the same channel as Video A
- Validating channel ownership during video submission
- Determining if video is from creator's channel vs another channel

## How it works

The validation process:
1. Get the channel ID of the submitted video
2. Compare against creator's registered channels
3. Return pass/fail with ownership status

## Dependencies

### Option 1: YouTube Data API v3 (Recommended)

Get an API key from [Google Cloud Console](https://console.cloud.google.com/):
1. Create a project
2. Enable YouTube Data API v3
3. Create API credentials (API key)

Install google client:
```bash
pip install google-api-python-client
```

### Option 2: Scraping (No API key required)

```bash
pip install requests beautifulsoup4
```

## Step-by-step validation

### Option 1: Using YouTube Data API

```python
from googleapiclient.discovery import build

class YouTubeChannelVerifier:
    def __init__(self, api_key: str):
        self.youtube = build('youtube', 'v3', developerKey=api_key)

    def get_video_channel_id(self, video_id: str) -> str:
        """Get the channel ID that owns a video."""
        request = self.youtube.videos().list(
            part='snippet',
            id=video_id
        )
        response = request.execute()

        if response['items']:
            return response['items'][0]['snippet']['channelId']

        return None

    def get_channel_id_from_url(self, video_url: str) -> str:
        """Extract channel ID from video URL or ID."""
        # If already a channel ID
        if video_id.startswith('UC'):
            return video_id

        # Extract video ID and fetch
        import re
        match = re.search(r'v=([a-zA-Z0-9_-]{11})', video_url)
        if match:
            video_id = match.group(1)
            return self.get_video_channel_id(video_id)

        return None
```

### Option 2: Scraping Method

```python
import requests
from bs4 import BeautifulSoup
import re

def get_video_channel_scraping(video_id: str) -> str:
    """Get channel ID by scraping video page."""
    url = f"https://www.youtube.com/watch?v={video_id}"

    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
    }

    response = requests.get(url, headers=headers)
    soup = BeautifulSoup(response.text, 'html.parser')

    # Find channel link
    channel_link = soup.find('a', {'rel': 'channel'})

    if channel_link:
        href = channel_link.get('href', '')
        match = re.search(r'/channel/([a-zA-Z0-9_-]+)', href)
        if match:
            return match.group(1)

    return None
```

### Validate Channel Ownership

```python
def verify_channel_ownership(
    video_id: str,
    creator_channels: list,
    api_key: str = None,
    method: str = 'api'
) -> dict:
    """
    Verify if a video belongs to one of creator's channels.

    Args:
        video_id: YouTube video ID or URL
        creator_channels: List of channel IDs to check against
        api_key: YouTube Data API key (optional)
        method: 'api' or 'scraping'

    Returns:
        Verification result dictionary
    """
    # Get the video's channel
    if method == 'api' and api_key:
        verifier = YouTubeChannelVerifier(api_key)
        video_channel_id = verifier.get_video_channel_id(video_id)
    else:
        video_channel_id = get_video_channel_scraping(video_id)

    if not video_channel_id:
        return {
            "valid": False,
            "error": "Could not determine video channel",
            "video_channel_id": None,
            "creator_channels": creator_channels
        }

    # Check if video's channel is in creator's channels
    is_own_channel = video_channel_id in creator_channels

    # Check if video's channel belongs to ANY creator (for slash decision)
    # This requires knowing all creators' channels - for now, just check own

    return {
        "valid": is_own_channel,
        "video_channel_id": video_channel_id,
        "creator_channels": creator_channels,
        "is_own_channel": is_own_channel
    }
```

## Usage Example

```python
result = verify_channel_ownership(
    video_id="SUBMITTED_VIDEO_ID",
    creator_channels=["UCxxx", "UCyyy", "UCzzz"],  # Creator's channels
    api_key="YOUR_YOUTUBE_API_KEY",
    method="api"
)

print(f"Valid: {result['valid']}")
print(f"Video channel: {result['video_channel_id']}")

if result['valid']:
    print("✅ Video posted on creator's channel")
else:
    print("❌ Video NOT on creator's channel")
    print("   - Check if it's another creator's channel")
```

## Decision Matrix

| Scenario | Result | Action |
|----------|--------|--------|
| Video on creator's channel | VALID | Count points |
| Video NOT on creator's channel | INVALID | Check if other creator's |
| Video on another known creator's channel | FOREIGN | Flag for SLASH |
| Channel unknown | INVALID | No points |

## Full Validation Pipeline

Run all three skills in order:

```python
def full_validate(
    video_a_id: str,          # Original pool video
    video_b_id: str,          # Submitted video
    creator_channels: list,   # Creator's registered channels
    api_key: str
) -> dict:
    """Run complete validation pipeline."""

    # Step 1: Transcript validation
    transcript_result = validate_transcript(
        video_a_id, video_b_id, threshold=0.70
    )

    if not transcript_result['valid']:
        return {
            "stage": "transcript",
            "valid": False,
            "reason": "transcript_mismatch",
            "score": transcript_result['score']
        }

    # Step 2: Frame validation
    frame_result = validate_frames(video_a_id, video_b_id)

    if not frame_result['valid']:
        return {
            "stage": "frames",
            "valid": False,
            "reason": "frame_mismatch",
            "score": frame_result['avg_ssim']
        }

    # Step 3: Channel validation
    channel_result = verify_channel_ownership(
        video_b_id, creator_channels, api_key
    )

    if not channel_result['valid']:
        # Need to check if it's another creator's channel
        return {
            "stage": "channel",
            "valid": False,
            "reason": "wrong_channel",
            "video_channel": channel_result['video_channel_id']
        }

    return {
        "stage": "complete",
        "valid": True,
        "transcript_score": transcript_result['score'],
        "frame_score": frame_result['avg_ssim']
    }
```

## Error Handling

1. **"API key invalid"**
   - Check Google Cloud Console
   - Verify YouTube Data API is enabled

2. **"Video unavailable"**
   - Video may be private/deleted
   - Return error gracefully

3. **"Channel not found"**
   - Scraper may need updating
   - YouTube may have changed layout

## Output Structure

```python
{
    "valid": bool,
    "video_channel_id": str|None,
    "creator_channels": [str],
    "is_own_channel": bool,
    "error": str|None
}
```

## Integration with Oracle

This skill integrates with the Oracle Agent:

1. Called after transcript + frame validation passes
2. If fails → log reason, no points
3. If foreign (belongs to another creator's known channel) → flag for SLASH

## API Key Security

Never commit API keys to git. Use environment variables:

```python
import os
API_KEY = os.environ.get('YOUTUBE_API_KEY')
```

In `.env`:
```
YOUTUBE_API_KEY=your_key_here
```

Add `.env` to `.gitignore` (already done in project).