"""YouTube channel verification service."""

from typing import Optional
from pytube import YouTube
from pytube.exceptions import VideoUnavailable


class ChannelService:
    """Verify YouTube video channel ownership."""

    @staticmethod
    def extract_video_id(url: str) -> str:
        """Extract video ID from URL."""
        import re
        patterns = [
            r"(?:youtube\.com/watch\?v=)([a-zA-Z0-9_-]{11})",
            r"(?:youtu\.be/)([a-zA-Z0-9_-]{11})",
            r"(?:youtube\.com/clip/)([a-zA-Z0-9_-]{11})",
        ]
        for pattern in patterns:
            match = re.search(pattern, url)
            if match:
                return match.group(1)
        return url

    def get_video_info(self, video_url: str) -> dict:
        """
        Get video information including channel.

        Returns dict with:
        - video_id: str
        - channel_id: str
        - channel_name: str
        """
        video_id = self.extract_video_id(video_url)

        try:
            yt = YouTube(video_url)
            return {
                "video_id": video_id,
                "channel_id": yt.channel_id,
                "channel_name": yt.channel_name,
                "title": yt.title,
            }
        except VideoUnavailable:
            raise RuntimeError(f"Video unavailable: {video_url}")
        except Exception as e:
            raise RuntimeError(f"Failed to get video info: {e}")

    def verify_channel(
        self,
        video_url: str,
        creator_channels: list[str]
    ) -> tuple[bool, Optional[str]]:
        """
        Verify if video belongs to one of creator's channels.

        Returns (is_valid, channel_id).
        """
        info = self.get_video_info(video_url)
        channel_id = info["channel_id"]

        is_valid = channel_id in creator_channels
        return is_valid, channel_id

    def verify_video_channel(
        self,
        video_url: str,
        creator_channels: list[str]
    ) -> tuple[bool, Optional[str]]:
        """Alias for verify_channel for API compatibility."""
        return self.verify_channel(video_url, creator_channels)

    def is_known_creator_channel(self, channel_id: str) -> bool:
        """
        Verifica se channel_id pertence a algum criador registrado no sistema.
        
        Consulta o banco de dados local para verificar se o canal
        já foi registrado por algum criador (initializeUser on-chain).
        
        Returns:
            True se o canal pertence a um criador conhecido
        """
        try:
            from ..db.database import Database
            db = Database()
            return db.is_channel_registered(channel_id)
        except Exception:
            return False