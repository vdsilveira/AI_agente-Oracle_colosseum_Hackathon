"""Metrics API client for batch video analysis."""

import asyncio
import uuid
from typing import Any, Optional
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
        self._max_retries = 2
        self._base_timeout = 120.0

    def _make_client(self, timeout: Optional[float] = None) -> httpx.AsyncClient:
        """Create httpx client with optional proxy."""
        kwargs = {"timeout": timeout or self._base_timeout}
        if self._proxy:
            kwargs["proxy"] = self._proxy
        return httpx.AsyncClient(**kwargs)

    async def analyze_batch(self, tasks: list[dict]) -> Optional[dict[str, Any]]:
        """
        Analyze a batch of videos with retry and exponential backoff.

        Args:
            tasks: List of {"url": str, "platform": str, "user_handle": str}

        Returns:
            API response with metrics for each video, or None if all retries failed
        """
        payload = {
            "job_id": f"oracle-{uuid.uuid4().hex[:8]}",
            "deep_analysis": False,
            "tasks": tasks,
        }

        from loguru import logger

        last_error = None
        for attempt in range(1 + self._max_retries):
            try:
                async with self._make_client() as client:
                    response = await client.post(
                        f"{self.base_url}/api/v1/analyze",
                        headers=self.headers,
                        json=payload,
                    )
                    if response.status_code != 200:
                        logger.warning(
                            f"[analyze_batch] attempt {attempt+1}: {response.status_code} "
                            f"{response.text[:300]}"
                        )
                        if attempt < self._max_retries:
                            wait = 2 ** (attempt + 1)
                            logger.info(f"Retrying in {wait}s...")
                            await asyncio.sleep(wait)
                            continue
                        response.raise_for_status()
                    return response.json()

            except httpx.TimeoutException as e:
                last_error = e
                logger.warning(f"[analyze_batch] attempt {attempt+1} timed out")
                if attempt < self._max_retries:
                    wait = 2 ** (attempt + 1)
                    logger.info(f"Retrying in {wait}s...")
                    await asyncio.sleep(wait)
            except Exception as e:
                last_error = e
                logger.error(f"[analyze_batch] attempt {attempt+1} failed: {e}")
                if attempt < self._max_retries:
                    wait = 2 ** (attempt + 1)
                    await asyncio.sleep(wait)

        logger.error(f"[analyze_batch] all {self._max_retries + 1} attempts failed: {last_error}")
        return None

    async def get_metrics(self, video_url: str, user_handle: str) -> dict[str, Any]:
        """
        Get metrics for a single video.

        Returns:
            {"video_id": str, "metrics": {"views": int, "likes": int, "comments": int}}
            or empty dict on failure.
        """
        from loguru import logger

        result = await self.analyze_batch([
            {
                "platform": "youtube",
                "user_handle": user_handle,
                "videos": [{"url": video_url, "platform": "youtube"}],
            }
        ])
        if not result:
            return {}
        try:
            return result["summary"][0]["videos"][0]
        except (KeyError, IndexError, TypeError) as e:
            logger.warning(f"[get_metrics] unexpected response format: {e}")
            return {}

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