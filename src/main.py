"""Main entry point for Oracle Agent."""

import asyncio
import signal
from loguru import logger

from .config import config
from .oracle.validator import OracleValidator
from .oracle.types import ValidationStatus
from .services.metrics_api_client import MetricsApiClient
from .db.database import Database


class OracleAgent:
    """Main oracle agent orchestrator."""

    def __init__(self):
        self.validator = OracleValidator()
        self.metrics_api = MetricsApiClient()
        self.db = Database(config.DATABASE_URL.replace("sqlite:///", ""))
        self.running = False

    async def validate_submission(
        self,
        video_a_id: str,
        video_b_url: str,
        creator_channels: list[str],
        entry_pda: str,
        pool_pda: str,
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
            return "fraud"
        elif result.status != ValidationStatus.VALID:
            logger.warning(f"Validation failed: {result.reason}")
            return "invalid"

        return "valid"

    async def update_metrics(self, entries: list[dict]):
        """Update metrics for valid entries."""
        if not entries:
            return

        logger.info(f"Updating metrics for {len(entries)} entries")

        tasks = [
            {"url": entry["clip_link"], "platform": "youtube", "user_handle": entry["user"]}
            for entry in entries
        ]

        try:
            result = await self.metrics_api.analyze_batch(tasks)

            for summary in result["summary"]:
                for video in summary["videos"]:
                    entry = next(
                        (e for e in entries if e["clip_link"] == video["url"]),
                        None
                    )
                    if entry:
                        metrics = video["metrics"]
                        score = self._calculate_score(metrics)

                        self.db.save_metrics(
                            entry_pda=entry["entry_pda"],
                            views=metrics["views"],
                            likes=metrics["likes"],
                            comments=metrics["comments"],
                            score=score,
                        )

                        logger.info(
                            f"Updated {entry['entry_pda']}: "
                            f"V={metrics['views']} L={metrics['likes']} C={metrics['comments']}"
                        )

        except Exception as e:
            logger.error(f"Failed to update metrics: {e}")

    @staticmethod
    def _calculate_score(metrics: dict) -> int:
        """Calculate weighted score from metrics."""
        views = metrics.get("views", 0)
        likes = metrics.get("likes", 0)
        comments = metrics.get("comments", 0)

        return int(views + likes * 10 + comments * 50)

    async def run(self):
        """Run the oracle agent polling loop."""
        self.running = True
        logger.info("Oracle Agent started")

        while self.running:
            try:
                logger.debug("Polling for updates...")

                await asyncio.sleep(config.POLL_INTERVAL_SECONDS)

            except asyncio.CancelledError:
                logger.info("Oracle Agent stopped")
                break
            except Exception as e:
                logger.error(f"Error in polling loop: {e}")

        self.running = False

    def stop(self):
        """Stop the oracle agent."""
        self.running = False


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