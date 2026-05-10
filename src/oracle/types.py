"""Oracle data types and models."""

from enum import Enum
from pydantic import BaseModel
from typing import Optional


class ValidationStatus(str, Enum):
    """Status of video submission validation."""

    VALID = "valid"
    WRONG_CHANNEL = "wrong_channel"
    INVALID_CHANNEL = "invalid_channel"
    INVALID_TRANSCRIPT = "invalid_transcript"
    INVALID_FRAMES = "invalid_frames"
    FRAUD = "fraud"
    ERROR = "error"


class ValidationResult(BaseModel):
    """Result of video validation."""

    status: ValidationStatus
    video_a_id: str
    video_b_url: str
    video_b_id: Optional[str] = None
    score: Optional[float] = None
    frame_score: Optional[float] = None
    channel_id: Optional[str] = None
    reason: Optional[str] = None
    is_valid: bool = False


class VideoMetrics(BaseModel):
    """Video engagement metrics."""

    video_id: str
    title: str
    views: int
    likes: int
    comments: int
    channel_name: Optional[str] = None


class PoolEntry(BaseModel):
    """Participant entry in a pool."""

    entry_pda: str
    pool_pda: str
    user: str
    channel_id: str
    clip_link: str
    views: int = 0
    likes: int = 0
    comments: int = 0
    score: int = 0
    validation_status: ValidationStatus = ValidationStatus.VALID


class PoolInfo(BaseModel):
    """Pool information."""

    pool_pda: str
    original_video_id: str
    creator: str
    status: str
    expiry_timestamp: int
    participant_count: int