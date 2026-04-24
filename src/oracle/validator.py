"""Oracle video submission validator."""

from loguru import logger
from ..config import config
from ..services.transcript_service import TranscriptService
from ..services.channel_service import ChannelService
from .types import ValidationStatus, ValidationResult


class OracleValidator:
    """Validates video submissions for the oracle."""

    def __init__(self):
        self.transcript_service = TranscriptService()
        self.channel_service = ChannelService()

    async def validate(
        self,
        video_a_id: str,
        video_b_url: str,
        creator_channels: list[str],
    ) -> ValidationResult:
        """
        Validate a video submission.

        Args:
            video_a_id: Original video ID (from pool)
            video_b_url: URL of submitted clip
            creator_channels: List of creator's channel IDs

        Returns:
            ValidationResult with status and details
        """
        logger.info(f"Validating {video_b_url} against {video_a_id}")

        try:
            result = ValidationResult(
                status=ValidationStatus.ERROR,
                video_a_id=video_a_id,
                video_b_url=video_b_url,
                is_valid=False,
            )

            video_b_id = self.channel_service.extract_video_id(video_b_url)
            result.video_b_id = video_b_id

            is_valid_channel, channel_id = self.channel_service.verify_channel(
                video_b_url, creator_channels
            )
            result.channel_id = channel_id

            if not is_valid_channel:
                logger.warning(f"Channel {channel_id} not in creator's channels: {creator_channels}")
                
                is_known = self.channel_service.is_known_creator_channel(channel_id)
                
                if is_known:
                    result.status = ValidationStatus.WRONG_CHANNEL
                    result.reason = f"Video posted on creator's other channel: {channel_id}"
                    logger.warning(f"WRONG_CHANNEL: Entry from known channel {channel_id}")
                else:
                    result.status = ValidationStatus.FRAUD
                    result.reason = f"Video channel {channel_id} not owned by creator or any known creator"
                    logger.warning(f"FRAUD DETECTED: Channel {channel_id} is unknown")
                return result

            transcript_a = self.transcript_service.get_transcript(video_a_id)
            transcript_b = self.transcript_service.get_transcript(video_b_id)
            transcript_score = self.transcript_service.compare_transcripts(transcript_a, transcript_b)

            result.score = transcript_score
            logger.info(f"Transcript score: {transcript_score:.2%}")

            if transcript_score < config.TRANSCRIPT_MIN_SCORE:
                result.status = ValidationStatus.INVALID_TRANSCRIPT
                result.reason = f"Transcript score {transcript_score:.2%} < {config.TRANSCRIPT_MIN_SCORE:.2%}"
                return result

            frame_score = await self._validate_frames(video_a_id, video_b_id)
            result.frame_score = frame_score
            logger.info(f"Frame score: {frame_score:.2%}")

            if frame_score < config.FRAME_MIN_MATCHES:
                result.status = ValidationStatus.INVALID_FRAMES
                result.reason = f"Frame score {frame_score:.2%} < {config.FRAME_MIN_MATCHES}/5"
                return result

            result.status = ValidationStatus.VALID
            result.is_valid = True
            logger.success(f"Validation PASSED for {video_b_url}")

            return result

        except Exception as e:
            logger.error(f"Validation error: {e}")
            return ValidationResult(
                status=ValidationStatus.ERROR,
                video_a_id=video_a_id,
                video_b_url=video_b_url,
                reason=str(e),
                is_valid=False,
            )

    async def _validate_frames(
        self,
        video_a_id: str,
        video_b_id: str,
    ) -> float:
        """
        Validate frames using SSIM.

        Returns number of frames that passed (out of FRAME_TOTAL_SAMPLES).
        """
        from ..services.similarity_service import SimilarityService

        similarity = SimilarityService()
        return await similarity.compare_videos(
            video_a_id,
            video_b_id,
            threshold=config.FRAME_SIMILARITY_THRESHOLD,
            num_samples=config.FRAME_TOTAL_SAMPLES,
        )