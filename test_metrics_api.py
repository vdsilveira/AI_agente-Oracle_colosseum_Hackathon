#!/usr/bin/env python3
"""Test Metrics API connectivity and endpoints."""

import asyncio
import httpx
from src.config import config
from src.services.metrics_api_client import MetricsApiClient
from loguru import logger

logger.enable("src")


async def test_api_connectivity():
    """Test basic API connectivity."""
    logger.info("=" * 80)
    logger.info("METRICS API CONNECTIVITY TEST")
    logger.info("=" * 80)

    api_url = config.METRICS_API_URL
    api_key = config.APP_API_KEY
    logger.info(f"API URL: {api_url}")
    logger.info(f"API Key: {api_key[:10]}...")

    # Test 1: Health check
    logger.info("\n[TEST 1] Health check...")
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(f"{api_url}/health")
            logger.info(f"Status: {response.status_code}")
            logger.info(f"Response: {response.text[:200]}")
    except Exception as e:
        logger.error(f"Health check failed: {e}")

    # Test 2: Batch analysis endpoint
    logger.info("\n[TEST 2] Batch analysis endpoint...")
    try:
        client = MetricsApiClient()
        result = await client.analyze_batch([
            {
                "url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
                "platform": "youtube",
                "user_handle": "test_user"
            }
        ])
        logger.info(f"Batch analysis result: {result}")
    except Exception as e:
        logger.error(f"Batch analysis failed: {e}")

    # Test 3: Validate ownership endpoint (new)
    logger.info("\n[TEST 3] Validate ownership endpoint...")
    try:
        client = MetricsApiClient()
        result = await client.validate_clip_ownership(
            clip_url="https://www.tiktok.com/@example/video/1234567890",
            editor_channels=["UCtest123456"]
        )
        logger.info(f"Ownership validation result: {result}")
    except Exception as e:
        logger.error(f"Ownership validation failed: {e}")

    logger.info("\n" + "=" * 80)
    logger.info("API CONNECTIVITY TEST COMPLETE")
    logger.info("=" * 80)


if __name__ == "__main__":
    asyncio.run(test_api_connectivity())
