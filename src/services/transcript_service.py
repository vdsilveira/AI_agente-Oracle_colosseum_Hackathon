"""YouTube transcript service."""

import re
from typing import Optional
from youtube_transcript_api import YouTubeTranscriptApi


class TranscriptService:
    """Fetch and compare YouTube video transcripts."""

    def __init__(self):
        self._api = YouTubeTranscriptApi()

    @staticmethod
    def extract_video_id(url: str) -> str:
        """Extract YouTube video ID from URL."""
        patterns = [
            r"(?:youtube\.com/watch\?v=)([a-zA-Z0-9_-]{11})",
            r"(?:youtu\.be/)([a-zA-Z0-9_-]{11})",
            r"(?:youtube\.com/embed/)([a-zA-Z0-9_-]{11})",
            r"(?:youtube\.com/clip/)([a-zA-Z0-9_-]{11})",
        ]

        for pattern in patterns:
            match = re.search(pattern, url)
            if match:
                return match.group(1)

        if len(url) == 11 and re.match(r"^[a-zA-Z0-9_-]{11}$", url):
            return url

        raise ValueError(f"Could not extract video ID from: {url}")

    def get_transcript(self, video_id: str) -> str:
        """Fetch transcript and return as plain text."""
        try:
            transcript = self._api.fetch(video_id, languages=['pt', 'en'])
            text_parts = [snippet.text for snippet in transcript]
            return " ".join(text_parts)
        except Exception as e:
            raise RuntimeError(f"Failed to fetch transcript for {video_id}: {e}")

    def get_transcript_with_timestamps(self, video_id: str) -> list[dict]:
        """Fetch transcript with timestamps."""
        try:
            transcript = self._api.fetch(video_id, languages=['pt', 'en'])
            return [
                {"start": snippet.start, "text": snippet.text}
                for snippet in transcript
            ]
        except Exception as e:
            raise RuntimeError(f"Failed to fetch transcript for {video_id}: {e}")

    @staticmethod
    def normalize_text(text: str) -> str:
        """Normalize text for comparison."""
        text = text.lower()
        text = re.sub(r"[^\w\s]", "", text)
        text = " ".join(text.split())
        return text

    def compare_transcripts(self, text_a: str, text_b: str) -> float:
        """
        Calculate similarity between two transcripts.

        Returns score between 0.0 and 1.0.
        """
        norm_a = self.normalize_text(text_a)
        norm_b = self.normalize_text(text_b)

        if not norm_b:
            return 0.0

        if norm_b in norm_a:
            return 1.0

        words_a = set(norm_a.split())
        words_b = norm_b.split()

        if not words_b:
            return 0.0

        matching_words = sum(1 for word in words_b if word in words_a)
        score = matching_words / len(words_b)

        return min(score, 1.0)