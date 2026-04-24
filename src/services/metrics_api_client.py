"""Metrics API client for batch video analysis."""

import uuid
from typing import Any
import httpx
from ..config import config


class MetricsApiClient:
    """Client for the metrics API."""

    def __init__(self):
        self.base_url = config.METRICS_API_URL
        self.headers = {
            "X-API-Key": config.JWT_TOKEN,
            "Content-Type": "application/json",
        }

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

        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                f"{self.base_url}/api/v1/analyze",
                headers=self.headers,
                json=payload,
            )
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