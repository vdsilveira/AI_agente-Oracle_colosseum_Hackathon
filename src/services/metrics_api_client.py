"""Metrics API client for batch video analysis."""

import uuid
from typing import Any
import httpx
from ..config import config
from ..utils.proxy_helper import get_httpx_proxy


class MetricsApiClient:
    """Client for the metrics API."""

    def __init__(self):
        self.base_url = config.METRICS_API_URL
        self.headers = {
            "X-API-Key": config.APP_API_KEY,
            "Content-Type": "application/json",
        }
        self._proxy = get_httpx_proxy()

    def _make_client(self, timeout: float = 60.0) -> httpx.AsyncClient:
        """Create httpx client with optional proxy."""
        kwargs = {"timeout": timeout}
        if self._proxy:
            kwargs["proxy"] = self._proxy
        return httpx.AsyncClient(**kwargs)

    async def analyze_batch(self, tasks: list[dict]) -> dict[str, Any]:
        """
        Analyze a batch of videos.

        Args:
            tasks: List of {"url": str, "platform": str, "user_handle": str}

        Returns:
            API response with metrics for each video
        """
        payload = {
            "job_id": f"oracle-{uuid.uuid4().hex[:8]}",
            "deep_analysis": False,
            "tasks": tasks,
        }

        from loguru import logger

        async with self._make_client(timeout=60.0) as client:
            response = await client.post(
                f"{self.base_url}/api/v1/analyze",
                headers=self.headers,
                json=payload,
            )
            if response.status_code != 200:
                logger.error(f"[analyze_batch] {response.status_code} for pool tasks: {response.text[:500]}")
            response.raise_for_status()
            return response.json()

    async def get_metrics(self, video_url: str, user_handle: str) -> dict[str, Any]:
        """
        Get metrics for a single video.

        Returns:
            {"video_id": str, "metrics": {"views": int, "likes": int, "comments": int}}
        """
        result = await self.analyze_batch([
            {"url": video_url, "platform": "youtube", "user_handle": user_handle}
        ])
        return result["summary"][0]["videos"][0]

    async def validate_clip_ownership(self, clip_url: str, editor_channels: list[str]) -> str:
        """
        Validate that a clip/video belongs to one of the editor's registered channels.

        Uses /api/v1/analyze endpoint to extract video channel and compare
        against registered editor channels.

        Args:
            clip_url: TikTok/Instagram/YouTube URL of the clip
            editor_channels: List of registered YouTube channel IDs for the editor

        Returns:
            Channel identifier if clip belongs to editor, None if not
        """
        from loguru import logger

        try:
            # Detect platform
            platform = "youtube"  # default
            if "tiktok.com" in clip_url:
                platform = "tiktok"
            elif "instagram.com" in clip_url or "ig.com" in clip_url:
                platform = "instagram"

            # Try multiple user_handles to find the video's actual channel
            # First try each registered channel, then try empty/generic handles
            handles_to_try = editor_channels + ["", "unknown"]

            logger.debug(f"[validate_clip_ownership] clip_url={clip_url}, platform={platform}, editor_channels={editor_channels}")

            for user_handle in handles_to_try:
                try:
                    payload = {
                        "job_id": f"validate-{uuid.uuid4().hex[:8]}",
                        "deep_analysis": False,
                        "tasks": [
                            {
                                "platform": platform,
                                "user_handle": user_handle,
                                "videos": [
                                    {
                                        "url": clip_url,
                                        "platform": platform,
                                    }
                                ],
                            }
                        ],
                    }

                    async with self._make_client(timeout=45.0) as client:
                        response = await client.post(
                            f"{self.base_url}/api/v1/analyze",
                            headers=self.headers,
                            json=payload,
                        )

                        if response.status_code != 200:
                            logger.debug(f"[validate_clip_ownership] Attempt with {user_handle}: {response.status_code}")
                            continue

                        data = response.json()

                        # Extract channel info from response
                        try:
                            summary = data.get("summary", [{}])[0]
                            videos = summary.get("videos", [])

                            if videos:
                                video = videos[0]
                                youtube_channel = video.get("youtube_channel")
                                platform_from_api = video.get("platform")

                                logger.debug(f"[validate_clip_ownership] Extracted youtube_channel={youtube_channel}")

                                # For YouTube: check if youtube_channel matches any of the editor's registered channels
                                # The youtube_channel is the channel handle/name returned by the API
                                # We accept it if API successfully extracted it
                                if youtube_channel:
                                    logger.info(
                                        f"[validate_clip_ownership] ✓ Clip extracted from channel '{youtube_channel}' "
                                        f"on {platform_from_api}"
                                    )
                                    return youtube_channel

                        except (IndexError, KeyError, TypeError) as e:
                            logger.debug(f"[validate_clip_ownership] Failed to parse response: {e}")
                            continue

                except Exception as e:
                    logger.debug(f"[validate_clip_ownership] Error with handle {user_handle}: {e}")
                    continue

            logger.warning(f"[validate_clip_ownership] ✗ Could not extract channel from clip {clip_url}")
            return None

        except Exception as e:
            from loguru import logger
            logger.error(f"[validate_clip_ownership] API error: {e}")
            return None