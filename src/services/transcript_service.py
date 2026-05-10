"""YouTube transcript service using Whisper STT."""

import asyncio
import os
import re
import tempfile
from typing import Optional
from faster_whisper import WhisperModel
from ..config import config


class TranscriptService:
    """Fetch video audio, transcribe with Whisper, compare transcripts."""

    def __init__(self):
        from loguru import logger
        model_size = config.WHISPER_MODEL_SIZE
        device = config.WHISPER_DEVICE
        self._model = WhisperModel(model_size, device=device, compute_type="int8")
        self._cache: dict[str, str] = {}
        logger.info(f"[TranscriptService] Whisper loaded: model={model_size} device={device}")

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

    def download_audio(self, video_id: str) -> str:
        """Download audio from YouTube video using yt-dlp.

        Returns path to downloaded WAV file.
        """
        from yt_dlp import YoutubeDL
        from loguru import logger

        url = f"https://www.youtube.com/watch?v={video_id}"
        tmpdir = tempfile.mkdtemp(prefix="whisper_")
        outtmpl = os.path.join(tmpdir, "%(id)s.%(ext)s")

        ydl_opts = {
            "format": "bestaudio/best",
            "outtmpl": outtmpl,
            "postprocessors": [{
                "key": "FFmpegExtractAudio",
                "preferredcodec": "wav",
            }],
            "quiet": True,
            "no_warnings": True,
            "proxy": "",
            "extractor_args": {"youtube": {"player_client": ["android"]}},
            "http_headers": {
                "User-Agent": "Mozilla/5.0 (Linux; Android 13) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.6099.144 Mobile Safari/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.5",
            },
        }

        with YoutubeDL(ydl_opts) as ydl:
            logger.info(f"[TranscriptService] Downloading audio: {video_id}")
            ydl.download([url])
            audio_path = outtmpl.replace("%(id)s.%(ext)s", f"{video_id}.wav")
            if os.path.exists(audio_path):
                logger.info(f"[TranscriptService] Audio saved: {audio_path}")
                return audio_path
            for f in os.listdir(tmpdir):
                if f.endswith(".wav"):
                    return os.path.join(tmpdir, f)
            raise RuntimeError(f"Audio file not found for {video_id}")

    def _transcribe_sync(self, video_id: str, audio_path: str) -> str:
        """Run Whisper transcription (blocking, called from thread pool)."""
        from loguru import logger
        logger.info(f"[TranscriptService] Transcribing: {video_id}")
        segments, info = self._model.transcribe(
            audio_path,
            language="pt",
            beam_size=1,
            vad_filter=True,
            vad_parameters=dict(min_silence_duration_ms=500),
        )
        text_parts = [seg.text.strip() for seg in segments]
        result = " ".join(text_parts)
        logger.info(f"[TranscriptService] Transcribed {video_id}: {len(result)} chars ({info.duration:.0f}s audio)")
        return result

    def get_transcript(self, video_id: str) -> str:
        """Fetch and transcribe audio, return text. Caches results."""
        if video_id in self._cache:
            return self._cache[video_id]

        audio_path = None
        try:
            audio_path = self.download_audio(video_id)
            result = self._transcribe_sync(video_id, audio_path)
            self._cache[video_id] = result
            return result
        except Exception as e:
            raise RuntimeError(f"Failed to transcribe {video_id}: {e}")
        finally:
            if audio_path and os.path.exists(audio_path):
                os.unlink(audio_path)
                parent = os.path.dirname(audio_path)
                if os.path.exists(parent):
                    try:
                        os.rmdir(parent)
                    except OSError:
                        pass

    async def get_transcripts_parallel(self, video_ids: list[str]) -> dict[str, str]:
        """Download and transcribe multiple videos in parallel (I/O + CPU)."""
        from loguru import logger
        loop = asyncio.get_running_loop()
        tasks = {}
        results = {}

        # Pre-check cache
        remaining = [v for v in video_ids if v not in self._cache]

        for vid in remaining:
            tasks[vid] = loop.run_in_executor(None, self._download_and_transcribe, vid)

        if tasks:
            logger.info(f"[TranscriptService] Transcribing {len(tasks)} videos in parallel")
            done = await asyncio.gather(*tasks.values(), return_exceptions=True)
            for vid, res in zip(tasks.keys(), done):
                if isinstance(res, Exception):
                    logger.error(f"[TranscriptService] Failed {vid}: {res}")
                    raise res
                self._cache[vid] = res
                results[vid] = res

        # Return cached + fresh
        for vid in video_ids:
            if vid in self._cache:
                results[vid] = self._cache[vid]

        return results

    def _download_and_transcribe(self, video_id: str) -> str:
        """Download + transcribe a single video (runs in executor)."""
        from loguru import logger
        audio_path = None
        try:
            audio_path = self.download_audio(video_id)
            result = self._transcribe_sync(video_id, audio_path)
            return result
        except Exception as e:
            raise RuntimeError(f"Failed to transcribe {video_id}: {e}")
        finally:
            if audio_path and os.path.exists(audio_path):
                os.unlink(audio_path)
                parent = os.path.dirname(audio_path)
                if os.path.exists(parent):
                    try:
                        os.rmdir(parent)
                    except OSError:
                        pass

    def get_transcript_with_timestamps(self, video_id: str) -> list[dict]:
        """Fetch transcript with timestamps."""
        from loguru import logger

        audio_path = None
        try:
            audio_path = self.download_audio(video_id)
            segments, info = self._model.transcribe(
                audio_path, language="pt", beam_size=1,
                vad_filter=True, vad_parameters=dict(min_silence_duration_ms=500),
            )
            result = [
                {"start": round(seg.start, 2), "text": seg.text.strip()}
                for seg in segments
            ]
            return result
        except Exception as e:
            raise RuntimeError(f"Failed to transcribe {video_id}: {e}")
        finally:
            if audio_path and os.path.exists(audio_path):
                os.unlink(audio_path)
                parent = os.path.dirname(audio_path)
                if os.path.exists(parent):
                    try:
                        os.rmdir(parent)
                    except OSError:
                        pass

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
