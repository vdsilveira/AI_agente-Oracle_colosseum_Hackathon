"""Main entry point for Oracle Agent."""

import asyncio
import hashlib
import signal
from loguru import logger
from typing import Optional

from .config import config
from .oracle.validator import OracleValidator
from .oracle.types import ValidationStatus
from .services.metrics_api_client import MetricsApiClient
from .services.alert_service import AlertService
from .db.database import Database
from .solana.connection import SolanaConnection, OracleCPI, create_oracle_connection


class OracleAgent:
    """Main oracle agent orchestrator."""

    def __init__(
        self,
        rpc_url: str = "https://api.devnet.solana.com",
        oracle_keypair_path: str = "keys/oracle.json",
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
            path = config.ORACLE_KEYPAIR_PATH if self.oracle_keypair_path == "keys/oracle.json" else self.oracle_keypair_path
            self._connection = SolanaConnection(self.rpc_url, path)
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
        video_b_url: str,
        creator_channels: list[str],
        entry_pda: str,
        pool_pda: str,
        editor_wallet: str = "",
        creator_wallet: str = "",
    ):
        """Validate a new submission."""
        logger.info(f"Validating submission for {entry_pda}")

        result = await self.validator.validate(
            video_a_id=video_a_id,
            video_b_url=video_b_url,
            creator_channels=creator_channels,
        )

        self.db.save_validation({
            "entry_pda": entry_pda,
            "pool_pda": pool_pda,
            "video_a_id": video_a_id,
            "video_b_id": result.video_b_id or "",
            "status": result.status.value,
            "transcript_score": result.score,
            "frame_score": result.frame_score,
            "reason": result.reason,
        })

        if result.status == ValidationStatus.FRAUD:
            logger.warning(f"FRAUD DETECTED: {result.reason}")
            await self.alert_service.notify_fraud(
                entry_pda=entry_pda,
                user_wallet=editor_wallet,
                reason=result.reason or "Unknown channel",
            )
            await self._slash_fraudulent_user(entry_pda, pool_pda)
            return "fraud"
        elif result.status == ValidationStatus.WRONG_CHANNEL:
            logger.warning(f"WRONG_CHANNEL: {result.reason}")
            await self.alert_service.notify_wrong_channel(
                entry_pda=entry_pda,
                creator_wallet=creator_wallet,
                editor_wallet=editor_wallet,
                clip_channel_id=result.channel_id or "",
                reason=result.reason or "Wrong channel from creator",
            )
            return "wrong_channel"
        elif result.status != ValidationStatus.VALID:
            logger.warning(f"Validation failed: {result.reason}")
            return "invalid"

        return "valid"

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
            logger.debug(f"Found {len(pools)} active pools")
            return pools
        except Exception as e:
            logger.error(f"Failed to check active pools: {e}")
            return []

    async def check_new_entries(self, pool_pda: str) -> list[dict]:
        """Check for new entries in a pool."""
        try:
            conn = await self.connection
            entries = await conn.get_entries_for_pool(pool_pda)
            new_entries = [e for e in entries if e.get("score", 0) == 0]
            logger.debug(f"Found {len(new_entries)} new entries for pool {pool_pda}")
            return new_entries
        except Exception as e:
            logger.error(f"Failed to check entries: {e}")
            return []

    async def update_all_metrics(self, pools: list[dict]):
        """Update metrics for all pools."""
        if not pools:
            return

        conn = await self.connection

        for pool in pools:
            pool_pda = pool.get("pool_pda") or str(pool.get("pubkey", ""))
            if not pool_pda:
                continue

            try:
                entries = await conn.get_entries_for_pool(pool_pda)
                valid_entries = [
                    e for e in entries
                    if e.get("score", 0) > 0 and not e.get("claimed", False)
                ]

                if not valid_entries:
                    continue

                logger.info(f"Updating metrics for {len(valid_entries)} entries in pool {pool_pda}")

                tasks = [
                    {
                        "url": entry.get("clip_link", ""),
                        "platform": "youtube",
                        "user_handle": entry.get("user", "")
                    }
                    for entry in valid_entries
                ]

                result = await self.metrics_api.analyze_batch(tasks)

                cpi = await self.oracle_cpi

                for summary in result.get("summary", []):
                    for video in summary.get("videos", []):
                        entry = next(
                            (e for e in valid_entries if e.get("clip_link") == video.get("url")),
                            None
                        )
                        if not entry:
                            continue

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

                        entry_pda = entry.get("entry_pda") or str(entry.get("pubkey", ""))
                        if entry_pda:
                            link_hash = hashlib.sha256(
                                entry.get("clip_link", "").encode()
                            ).digest()

                            try:
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
                            except Exception as e:
                                logger.error(f"Failed to update metrics: {e}")

                        self.db.save_metrics(
                            entry_pda=entry_pda,
                            views=views,
                            likes=likes,
                            comments=comments,
                            score=score,
                        )

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
                        
                        creator = pool.get("creator", "")
                        
                        creator_channels = []
                        if creator:
                            try:
                                creator_channels = await conn.get_creator_channels(creator)
                            except Exception as e:
                                logger.warning(f"Failed to get creator channels for {creator}: {e}")
                                continue
                        
                        if not creator_channels:
                            logger.warning(f"No channels registered for creator {creator}, skipping validation")
                            continue
                        
                        new_entries = await self.check_new_entries(pool_pda)
                        
                        for entry in new_entries:
                            video_a_id = pool.get("original_video_id", "")
                            video_b_url = entry.get("clip_link", "")
                            entry_pda = entry.get("entry_pda") or str(entry.get("pubkey", ""))
                            editor_wallet = entry.get("user", "")
                            
                            logger.info(f"Validating new entry: {entry_pda}")
                            
                            result = await self.validate_submission(
                                video_a_id=video_a_id,
                                video_b_url=video_b_url,
                                creator_channels=creator_channels,
                                entry_pda=entry_pda,
                                pool_pda=pool_pda,
                                editor_wallet=editor_wallet,
                                creator_wallet=creator,
                            )
                            
                            if result == "valid":
                                logger.success(f"Entry {entry_pda} validated successfully")
                            elif result == "wrong_channel":
                                logger.warning(f"Entry {entry_pda} wrong channel, skipped")
                            elif result == "fraud":
                                logger.error(f"Entry {entry_pda} fraud detected, user slashed")
                            elif result == "invalid":
                                logger.warning(f"Entry {entry_pda} invalid: {result}")
                    
                    await self.update_all_metrics(pools)
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