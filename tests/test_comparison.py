import pytest
from src.services.transcript_service import TranscriptService
from src.services.similarity_service import SimilarityService


VIDEO_A = "https://www.youtube.com/watch?v=sxLdYU_lMo0&t=1634s"
VIDEO_B = "https://www.youtube.com/watch?v=PAWyo9lL3tw"


@pytest.fixture
def video_a_url():
    return VIDEO_A


@pytest.fixture
def video_b_url():
    return VIDEO_B


@pytest.fixture
def video_a_id():
    return TranscriptService.extract_video_id(VIDEO_A)


@pytest.fixture
def video_b_id():
    return TranscriptService.extract_video_id(VIDEO_B)


@pytest.fixture
def transcript_service():
    return TranscriptService()


@pytest.fixture
def similarity_service():
    return SimilarityService()


def test_transcript_similarity(transcript_service, video_a_id, video_b_id):
    """Test that Video B transcript is ≥70% similar to Video A."""
    text_a = transcript_service.get_transcript(video_a_id)
    text_b = transcript_service.get_transcript(video_b_id)

    score = transcript_service.compare_transcripts(text_a, text_b)
    print(f"Transcript similarity: {score:.2f}")
    assert score >= 0.70, f"Transcript similarity {score:.2f} < 0.70"


@pytest.mark.asyncio
async def test_frame_similarity(similarity_service, video_a_id, video_b_id):
    """Test that ≥3 of 5 frames have SSIM ≥0.70."""
    passed = await similarity_service.compare_videos(
        video_a_id=video_a_id,
        video_b_id=video_b_id,
        threshold=0.70,
        num_samples=5,
    )

    print(f"Frame similarity: {passed}/5 passed")
    assert passed >= 3, f"Frame similarity: {passed}/5 passed (need ≥3)"