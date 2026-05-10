#!/usr/bin/env python3
"""Test Oracle Agent flow."""

import asyncio
from src.main import OracleAgent
from src.config import config
from loguru import logger

logger.enable("src")


async def test_oracle_flow():
    """Test complete Oracle Agent flow."""
    agent = OracleAgent()

    logger.info("=" * 80)
    logger.info("ORACLE AGENT TEST FLOW")
    logger.info("=" * 80)

    # Test 1: Check active pools
    logger.info("\n[TEST 1] Checking active pools...")
    pools = await agent.check_active_pools()
    logger.info(f"Found {len(pools)} active pools")
    for pool in pools[:3]:  # Show first 3
        logger.info(f"  - Pool: {pool.get('pubkey', 'unknown')}")
        logger.info(f"    Creator: {pool.get('creator', 'unknown')}")
        logger.info(f"    Video ID: {pool.get('original_video_id', 'unknown')}")
        logger.info(f"    Status: {pool.get('status', 'unknown')}")

    if not pools:
        logger.warning("No active pools found. Skipping further tests.")
        return

    # Test 2: Check entries for first pool
    logger.info("\n[TEST 2] Checking entries for first pool...")
    pool_pda = pools[0].get("pool_pda") or pools[0].get("pubkey")
    entries = await agent.check_new_entries(pool_pda)
    logger.info(f"Found {len(entries)} new entries (score=0)")
    for entry in entries[:2]:  # Show first 2
        logger.info(f"  - Entry: {entry.get('pubkey', 'unknown')}")
        logger.info(f"    User: {entry.get('user', 'unknown')}")
        logger.info(f"    Clip: {entry.get('clip_link', 'unknown')}")
        logger.info(f"    Score: {entry.get('score', 0)}")

    if entries:
        # Test 3: Validate editor authorship
        logger.info("\n[TEST 3] Validating editor authorship...")
        entry = entries[0]
        editor_wallet = entry.get("user", "")
        clip_url = entry.get("clip_link", "")

        if editor_wallet and clip_url:
            result = await agent.validate_editor_authorship(
                clip_url=clip_url,
                entry_pda=entry.get("pubkey", ""),
                pool_pda=pool_pda,
                editor_wallet=editor_wallet,
            )
            logger.info(f"Authorship validation result: {result}")
        else:
            logger.warning(f"Missing data: wallet={editor_wallet}, url={clip_url}")

    # Test 4: Check metrics API
    logger.info("\n[TEST 4] Testing MetricsAPI connection...")
    try:
        result = await agent.metrics_api.validate_clip_ownership(
            clip_url="https://www.tiktok.com/@example/video/1234567890",
            editor_channels=["UCtest123456"],
        )
        logger.info(f"API response: {result}")
    except Exception as e:
        logger.error(f"MetricsAPI error: {e}")

    logger.info("\n" + "=" * 80)
    logger.info("TEST FLOW COMPLETE")
    logger.info("=" * 80)


if __name__ == "__main__":
    asyncio.run(test_oracle_flow())
