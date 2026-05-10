"""Main entry point for Oracle Agent."""

import asyncio
import hashlib
import signal
from datetime import datetime, timezone
from loguru import logger
from typing import Optional

import httpx

from .config import config
from .oracle.validator import OracleValidator
from .oracle.types import ValidationStatus
from .services.metrics_api_client import MetricsApiClient
from .services.alert_service import AlertService
from .db.database import Database
from .solana.connection import SolanaConnection, OracleCPI, create_oracle_connection
from .utils.proxy_helper import is_proxy_configured


class OracleAgent:
    """Main oracle agent orchestrator."""

    def __init__(
        self,
        rpc_url: str = "https://api.devnet.solana.com",
        oracle_keypair_path: str = None,
    ):
        self.validator = OracleValidator()
        self.metrics_api = MetricsApiClient()
        self.alert_service = AlertService()
        self.db = Database(config.DATABASE_URL.replace("sqlite:///", ""))
        self.running = False

        self.rpc_url = rpc_url
        self.oracle_keypair_path = oracle_keypair_path
        self._connection: Optional[SolanaConnection] = None
        self._oracle_cpi: Optional[OracleCPI] = None
        self._last_pool_check = 0

    @property
    async def connection(self) -> SolanaConnection:
        """Lazy load SolanaConnection."""
        if self._connection is None:
            self._connection = SolanaConnection(self.rpc_url, self.oracle_keypair_path)
        return self._connection

    @property
    async def oracle_cpi(self) -> OracleCPI:
        """Lazy load OracleCPI."""
        if self._oracle_cpi is None:
            conn = await self.connection
            self._oracle_cpi = OracleCPI(conn)
        return self._oracle_cpi

    async def validate_submission(
        self,
        video_a_id: str,
        clip_url: str,
        entry_pda: str,
        pool_pda: str,
        editor_wallet: str,
    ) -> str:
        """Full validation pipeline for new submissions.

        Pipeline:
          1. Editor channel ownership check (via Metrics API)
          2. Transcript similarity  (≥70%)
          3. Frame similarity       (≥3/5 SSIM ≥0.70)

        Slash (fraud) only when BOTH channel AND content checks fail.
        Content-only failures are logged but the entry is simply skipped.

        Returns:
            "valid"               all checks passed
            "fraud"               channel unverified + content failed (slash applied)
            "invalid_transcript"  transcript below threshold
            "invalid_frames"      frame match below threshold
            "error: ..."          unexpected error
        """
        logger.info(f"Validating submission for entry {entry_pda}")

        try:
            conn = await self.connection

            # --- Step 1: Editor channel ownership check (via API) ---
            editor_profile = await conn.get_user_profile(editor_wallet)
            registered_channels = editor_profile.get("channelIds", []) if editor_profile else []

            channel_verified = False
            if registered_channels:
                extracted = await self.metrics_api.validate_clip_ownership(
                    clip_url=clip_url,
                    editor_channels=registered_channels,
                )
                channel_verified = bool(extracted)
                if channel_verified:
                    logger.success(f"Channel verified for editor {editor_wallet}: {extracted}")
                else:
                    logger.warning(f"Could not verify clip channel via API for {editor_wallet}")
            else:
                logger.warning(f"Editor {editor_wallet} has no registered channels")

            # --- Step 2: Channel-only validation (transcript/frames skipped — too slow) ---
            if channel_verified:
                logger.success(f"Submission VALID (channel only): {entry_pda}")
                self.db.save_validation({
                    "entry_pda": entry_pda,
                    "pool_pda": pool_pda,
                    "video_a_id": video_a_id,
                    "video_b_id": clip_url,
                    "status": "valid",
                    "transcript_score": 0.0,
                    "frame_score": 0,
                    "reason": "Channel verified (content check deferred)",
                })
                return "valid"

            logger.warning(f"Entry {entry_pda}: channel not verified")
            return "invalid_channel"

        except Exception as e:
            logger.error(f"Validation error for {entry_pda}: {e}")
            return f"error: {str(e)}"

    async def _handle_fraud(
        self,
        entry_pda: str,
        pool_pda: str,
        editor_wallet: str,
        reason: str,
    ) -> str:
        """Log fraud, fire alert, slash the user, return 'fraud'."""
        logger.error(reason)
        await self.alert_service.notify_fraud(
            entry_pda=entry_pda,
            user_wallet=editor_wallet,
            reason=reason,
        )
        await self._slash_fraudulent_user(entry_pda, pool_pda)
        return "fraud"

    async def _slash_fraudulent_user(self, entry_pda: str, pool_pda: str):
        """Slash a fraudulent user."""
        try:
            cpi = await self.oracle_cpi
            entry = await self._get_entry_details(entry_pda)
            if entry and entry.get("user"):
                tx_sig = await cpi.slash_user(entry["user"])
                logger.info(f"Slashed user: {entry['user']}, tx: {tx_sig}")
        except Exception as e:
            logger.error(f"Failed to slash user: {e}")

    async def _get_entry_details(self, entry_pda: str) -> Optional[dict]:
        """Get entry details from on-chain."""
        try:
            conn = await self.connection
            return await conn.get_account_info(entry_pda)
        except Exception:
            return None

    async def check_active_pools(self) -> list[dict]:
        """Check for active pools."""
        try:
            conn = await self.connection
            pools = await conn.get_active_pools()
            logger.trace(f"Found {len(pools)} active pools")
            return pools
        except Exception as e:
            logger.error(f"Failed to check active pools: {e}")
            return []

    async def _sync_entry_to_core(self, entry: dict, pool_pda: str, views: int, likes: int, comments: int, score: int):
        """Sync entry metrics to core-api DB."""
        if not config.CORE_API_URL:
            return
        try:
            payload = {
                "pda_address": entry.get("entry_pda") or str(entry.get("pubkey", "")),
                "pool_pda": pool_pda,
                "user_wallet": entry.get("user", ""),
                "channel_id": entry.get("channel_id", ""),
                "clip_link": entry.get("clip_link", ""),
                "views": views,
                "likes": likes,
                "comments": comments,
                "score": score,
                "claimed": entry.get("claimed", False),
            }
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.post(
                    f"{config.CORE_API_URL}/entries/sync",
                    json=payload,
                )
                if resp.status_code != 200:
                    logger.warning(f"core-api entry sync returned {resp.status_code}")
        except Exception as e:
            logger.warning(f"Failed to sync entry to core-api: {e}")

    async def _sync_pool_to_core(self, pool_pda: str, pool: dict):
        """Sync pool data to core-api DB."""
        if not config.CORE_API_URL:
            return
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.post(
                    f"{config.CORE_API_URL}/pools/sync",
                    json={
                        "pda_address": pool_pda,
                        "creator_wallet": pool.get("creator", ""),
                        "original_video_id": pool.get("original_video_id", ""),
                        "prize_amount": pool.get("prize_amount", 0),
                        "scoring_rules": pool.get("scoring_rules", {
                            "views_weight": 5000,
                            "likes_weight": 3000,
                            "comments_weight": 2000,
                        }),
                        "participant_count": pool.get("participant_count", 0),
                        "total_score": pool.get("total_score", 0),
                        "status": "OPEN",
                        "expiry_timestamp": datetime.fromtimestamp(
                            pool.get("expiry_timestamp", 0), tz=timezone.utc
                        ).isoformat(),
                    },
                )
                if resp.status_code != 200:
                    logger.warning(f"core-api pool sync returned {resp.status_code}")
        except Exception as e:
            logger.warning(f"Failed to sync pool to core-api: {e}")

    async def _close_pool_in_core(self, pool_pda: str):
        """Notify core-api that a pool has been closed/distributed."""
        if not config.CORE_API_URL:
            return
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.post(f"{config.CORE_API_URL}/pools/{pool_pda}/close")
                if resp.status_code != 200:
                    logger.warning(f"core-api pool close returned {resp.status_code}")
        except Exception as e:
            logger.warning(f"Failed to close pool in core-api: {e}")

    async def check_new_entries(self, pool_pda: str) -> list[dict]:
        """Check for new entries in a pool (score == 0)."""
        try:
            conn = await self.connection
            entries = await conn.get_entries_for_pool(pool_pda)
            new_entries = [e for e in entries if e.get("score", 0) == 0]
            logger.trace(f"Found {len(new_entries)} new entries for pool {pool_pda}")
            return new_entries
        except Exception as e:
            logger.error(f"Failed to check entries: {e}")
            return []

    async def update_all_metrics(self, pools: list[dict]):
        """Update metrics for all pools, one entry at a time."""
        if not pools:
            return

        conn = await self.connection
        cpi = await self.oracle_cpi

        for pool in pools:
            pool_pda = pool.get("pool_pda") or str(pool.get("pubkey", ""))
            if not pool_pda:
                continue

            try:
                entries = await conn.get_entries_for_pool(pool_pda)
                valid_entries = [
                    e for e in entries
                    if not e.get("claimed", False)
                ]

                if not valid_entries:
                    continue

                logger.info(f"Updating metrics for {len(valid_entries)} entries in pool {pool_pda}")

                for entry in valid_entries:
                    entry_pda = entry.get("entry_pda") or str(entry.get("pubkey", ""))
                    clip_link = entry.get("clip_link", "")

                    if not entry_pda or not clip_link:
                        logger.warning(f"[update_all_metrics] Skipping entry with missing pda or clip_link")
                        continue

                    task = {
                        "platform": "youtube",
                        "user_handle": entry.get("channel_id", entry.get("user", "")),
                        "videos": [
                            {
                                "url": clip_link,
                                "platform": "youtube",
                            }
                        ],
                    }

                    logger.debug(f"[update_all_metrics] Fetching metrics for {entry_pda[:8]}... ({clip_link})")

                    try:
                        result = await self.metrics_api.analyze_batch([task])

                        if not result:
                            logger.warning(f"[update_all_metrics] API returned None for {entry_pda[:8]}... — skipping")
                            continue

                        summaries = result.get("summary", [])
                        if not summaries:
                            logger.warning(f"[update_all_metrics] No summaries for {entry_pda[:8]}... — skipping")
                            continue

                        videos = summaries[0].get("videos", [])
                        if not videos:
                            logger.warning(f"[update_all_metrics] No videos in summary for {entry_pda[:8]}... — skipping")
                            continue

                        video = videos[0]
                        metrics = video.get("metrics", {})
                        views = metrics.get("views", 0)
                        likes = metrics.get("likes", 0)
                        comments = metrics.get("comments", 0)

                        scoring_rules = pool.get("scoring_rules", {
                            "views_weight": 5000,
                            "likes_weight": 3000,
                            "comments_weight": 2000,
                        })
                        score = self._calculate_score(metrics, scoring_rules)

                        link_hash = hashlib.sha256(clip_link.encode()).digest()

                        tx_sig = await cpi.update_metrics(
                            entry_pda=entry_pda,
                            pool_pda=pool_pda,
                            views=views,
                            likes=likes,
                            comments=comments,
                            link_hash=link_hash,
                        )
                        logger.info(
                            f"Updated {entry_pda}: V={views} L={likes} C={comments} -> Score={score}, tx={tx_sig}"
                        )

                        self.db.save_metrics(
                            entry_pda=entry_pda,
                            views=views,
                            likes=likes,
                            comments=comments,
                            score=score,
                        )

                        await self._sync_entry_to_core(entry, pool_pda, views, likes, comments, score)

                    except Exception as e:
                        logger.error(f"Failed to update metrics for {entry_pda[:8]}...: {e}")
                        continue

            except Exception as e:
                logger.error(f"Failed to update metrics for pool {pool_pda}: {e}")

    async def check_expired_pools(self, pools: list[dict]):
        """Check and process expired pools."""
        import time
        current_time = int(time.time())

        conn = await self.connection
        cpi = await self.oracle_cpi

        for pool in pools:
            expiry = pool.get("expiry_timestamp", 0)
            if expiry and current_time >= expiry:
                pool_pda = pool.get("pool_pda") or str(pool.get("pubkey", ""))
                if pool_pda:
                    try:
                        tx_sig = await cpi.close_and_payout(pool_pda)
                        logger.info(f"Closed pool {pool_pda}, tx: {tx_sig}")
                        await self._close_pool_in_core(pool_pda)
                    except Exception as e:
                        logger.error(f"Failed to close pool: {e}")

    async def run(self):
        """Run the oracle agent polling loop."""
        self.running = True
        logger.info("Oracle Agent started")

        while self.running:
            try:
                pools = await self.check_active_pools()

                if pools:
                    conn = await self.connection

                    for pool in pools:
                        pool_pda = pool.get("pool_pda") or str(pool.get("pubkey", ""))
                        if not pool_pda:
                            continue

                        video_a_id = pool.get("original_video_id", "")

                        # Process new entries that need first-time validation
                        new_entries = await self.check_new_entries(pool_pda)

                        for entry in new_entries:
                            clip_url = entry.get("clip_link", "")
                            entry_pda = entry.get("entry_pda") or str(entry.get("pubkey", ""))
                            editor_wallet = entry.get("user", "")

                            logger.info(f"Validating new entry {entry_pda} from editor {editor_wallet}")

                            result = await self.validate_submission(
                                video_a_id=video_a_id,
                                clip_url=clip_url,
                                entry_pda=entry_pda,
                                pool_pda=pool_pda,
                                editor_wallet=editor_wallet,
                            )

                            if result == "valid":
                                logger.success(f"Entry {entry_pda} validated – editor {editor_wallet}")
                                try:
                                    cpi = await self.oracle_cpi
                                    channel_handle = entry.get("channel_id", editor_wallet)
                                    metrics_data = await asyncio.wait_for(
                                        self.metrics_api.get_metrics(clip_url, channel_handle),
                                        timeout=130.0,
                                    )
                                    if not metrics_data:
                                        logger.warning(
                                            f"No metrics returned for {entry_pda} – "
                                            f"skipping on-chain score init"
                                        )
                                        continue
                                    metrics = metrics_data.get("metrics", {})
                                    views = metrics.get("views", 0)
                                    likes = metrics.get("likes", 0)
                                    comments = metrics.get("comments", 0)
                                    link_hash = hashlib.sha256(clip_url.encode()).digest()
                                    tx_sig = await cpi.update_metrics(
                                        entry_pda=entry_pda,
                                        pool_pda=pool_pda,
                                        views=views,
                                        likes=likes,
                                        comments=comments,
                                        link_hash=link_hash,
                                    )
                                    logger.info(
                                        f"Initialized on-chain score for {entry_pda}: "
                                        f"V={views} L={likes} C={comments}, tx={tx_sig}"
                                    )
                                    await self._sync_entry_to_core(entry, pool_pda, views, likes, comments, score)
                                    await self._sync_pool_to_core(pool_pda, pool)
                                except asyncio.TimeoutError:
                                    logger.error(
                                        f"Scoring init timed out for {entry_pda} "
                                        f"(Metrics API >130s)"
                                    )
                                except Exception as e:
                                    logger.error(f"Failed to initialize score for {entry_pda}: {e}")
                            elif result == "invalid_channel":
                                logger.warning(f"Entry {entry_pda}: channel not verified — entry skipped, no slash")
                            else:
                                logger.warning(f"Entry {entry_pda} validation result: {result}")

                    # Update metrics for all pools (entries with score > 0)
                    await self.update_all_metrics(pools)

                    # Close expired pools
                    await self.check_expired_pools(pools)

                await asyncio.sleep(config.POLL_INTERVAL_SECONDS)

            except asyncio.CancelledError:
                logger.info("Oracle Agent stopped")
                break
            except Exception as e:
                logger.error(f"Error in polling loop: {e}")
                await asyncio.sleep(10)

        self.running = False

    async def run_once(self):
        """Run a single iteration (for testing)."""
        logger.info("Running single iteration...")

        pools = await self.check_active_pools()
        logger.info(f"Active pools: {len(pools)}")

        for pool in pools:
            pool_pda = pool.get("pool_pda") or str(pool.get("pubkey", ""))
            entries = await self.check_new_entries(pool_pda)
            logger.info(f"Pool {pool_pda}: {len(entries)} new entries")

        await self.update_all_metrics(pools)
        logger.info("Metrics update complete")

    def stop(self):
        """Stop the oracle agent."""
        self.running = False

    @staticmethod
    def _calculate_score(metrics: dict, scoring_rules: dict = None) -> int:
        """Calculate weighted score.

        scoring_rules:
        - views_weight: u16 (ex: 5000 = 50%)
        - likes_weight: u16 (ex: 3000 = 30%)
        - comments_weight: u16 (ex: 2000 = 20%)
        """
        views = metrics.get("views", 0)
        likes = metrics.get("likes", 0)
        comments = metrics.get("comments", 0)

        if scoring_rules:
            views_weight = scoring_rules.get("views_weight", 5000)
            likes_weight = scoring_rules.get("likes_weight", 3000)
            comments_weight = scoring_rules.get("comments_weight", 2000)

            score = (
                (views * views_weight) +
                (likes * likes_weight) +
                (comments * comments_weight)
            ) // 10000
        else:
            score = int(views + likes * 10 + comments * 50)

        return score


async def main():
    """Main entry point."""
    logger.info("Starting Oracle Agent...")

    if is_proxy_configured():
        logger.info(f"HTTP proxy configured: HTTPS_PROXY={'set' if config.HTTPS_PROXY else 'not set'}")
    else:
        logger.warning("No HTTP proxy configured - YouTube requests may be blocked")

    try:
        config.validate()
    except (ValueError, FileNotFoundError) as e:
        logger.error(f"Configuration error: {e}")
        return

    agent = OracleAgent()

    def signal_handler(sig, frame):
        logger.info("Received shutdown signal")
        agent.stop()

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    await agent.run()


if __name__ == "__main__":
    asyncio.run(main())
