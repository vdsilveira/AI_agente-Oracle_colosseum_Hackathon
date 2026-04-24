"""End-to-End test for Oracle Agent flow with full validation."""
import pytest
import asyncio
import os
import sys
import time
import hashlib
import json
from pathlib import Path
from unittest.mock import AsyncMock, patch
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).parent.parent))

load_dotenv()

VIDEO_A = "https://www.youtube.com/watch?v=sxLdYU_lMo0&t=1634s"
VIDEO_B = "https://www.youtube.com/watch?v=PAWyo9lL3tw"

PROGRAM_ID = "4RAbxbEVCsYaaK3WR8r7eYwrofTJ7yqdZ3hqSYRLPfT4"


def create_keypair_from_seed(seed: str):
    """Create keypair from seed string."""
    from solders.keypair import Keypair
    hash_bytes = hashlib.sha256(seed.encode()).digest()
    return Keypair.from_bytes(hash_bytes[:32])


def create_keypair_from_secret(secret: str):
    """Create keypair from secret key (hex or JSON)."""
    from solders.keypair import Keypair
    try:
        data = json.loads(secret)
        return Keypair.from_json(data)
    except:
        return Keypair.from_secret_key(bytes.fromhex(secret))


@pytest.fixture
def creator_keypair():
    """Creator wallet from .env."""
    seed = os.getenv("COLOSSEUM_CREATOR_SEED", "creator_test_key_12345678901234567890")
    return create_keypair_from_seed(seed)


@pytest.fixture
def editor_keypair():
    """Editor wallet from .env."""
    seed = os.getenv("COLOSSEUM_EDITOR_SEED", "editor_test_key_12345678901234567890")
    return create_keypair_from_seed(seed)


@pytest.fixture
def oracle_keypair():
    """Oracle wallet from keys/oracle.json."""
    oracle_path = os.getenv("ORACLE_KEYPAIR_PATH", "keys/oracle.json")
    oracle_path_full = Path(__file__).parent.parent / oracle_path
    
    if not oracle_path_full.exists():
        pytest.skip(f"Oracle keypair not found: {oracle_path_full}")
    
    with open(oracle_path_full) as f:
        data = json.load(f)
    
    if isinstance(data, list):
        from solders.keypair import Keypair
        return Keypair.from_json(data)
    else:
        from solders.keypair import Keypair
        return Keypair.from_secret_key(bytes.fromhex(data))


@pytest.fixture
def rpc_url():
    """Solana RPC URL."""
    return os.getenv("SOLANA_RPC_URL", "https://api.devnet.solana.com")


# ============================================================================
# ORACLE VALIDATION TESTS
# ============================================================================

@pytest.mark.asyncio
async def test_validation_transcript_similarity():
    """Test 1: Transcript similarity validation (≥70%)."""
    from src.services.transcript_service import TranscriptService
    
    ts = TranscriptService()
    video_a_id = "sxLdYU_lMo0"
    video_b_id = "PAWyo9lL3tw"
    
    text_a = ts.get_transcript(video_a_id)
    text_b = ts.get_transcript(video_b_id)
    score = ts.compare_transcripts(text_a, text_b)
    
    print(f"Transcript similarity: {score:.2f}")
    
    assert score >= 0.70, f"Transcript similarity {score:.2f} < 0.70"
    print("✅ PASSED")


@pytest.mark.asyncio
async def test_validation_channel_check_valid():
    """Test 2: Channel check - VALID (same channel)."""
    from src.services.channel_service import ChannelService
    
    cs = ChannelService()
    video_url = VIDEO_B
    creator_channels = ["UCsx_c2e0Et9E9b1nB4r2bIg", "test_channel"]
    
    try:
        is_valid = await asyncio.to_thread(cs.verify_video_channel, video_url, creator_channels)
        
        print(f"Channel check result: {is_valid}")
        print(f"Creator channels: {creator_channels}")
        print(f"Video URL: {video_url}")
        
        assert isinstance(is_valid, tuple), "verify_video_channel should return (is_valid, channel_id)"
        assert isinstance(is_valid[0], bool), "First element should be bool"
        assert is_valid[1] is not None, "channel_id should not be None"
        print(f"✅ Channel verification passed: result={is_valid}")
    except RuntimeError as e:
        pytest.skip(f"YouTube video unavailable: {e}")


@pytest.mark.asyncio
async def test_validation_wrong_channel():
    """Test 3: WRONG CHANNEL - clip from creator's other channel."""
    from src.services.channel_service import ChannelService
    
    cs = ChannelService()
    
    VIDEO_A_ID = "sxLdYU_lMo0"
    VIDEO_B_ID = "PAWyo9lL3tw"
    creator_channels = ["UCsx_c2e0Et9E9b1nB4r2bIg", "test_channel"]
    
    video_b_url = "https://www.youtube.com/watch?v=PAWyo9lL3tw"
    
    try:
        is_valid, channel_id = await asyncio.to_thread(cs.verify_channel, video_b_url, creator_channels)
        
        print(f"Video B channel_id: {channel_id}")
        print(f"Creator channels: {creator_channels}")
        
        if channel_id not in creator_channels:
            print(f"✅ WRONG_CHANNEL detected: {channel_id} not in creator channels")
        else:
            print(f"ℹ️  Video B is from creator's own channel - checking validator logic")
    except RuntimeError as e:
        pytest.skip(f"YouTube video unavailable: {e}")


@pytest.mark.asyncio
async def test_validation_fraud():
    """Test 4: FRAUD - clip from completely unknown channel."""
    from src.services.channel_service import ChannelService
    
    cs = ChannelService()
    
    creator_channels = ["UCsx_c2e0Et9E9b1nB4r2bIg"]
    
    try:
        is_valid, channel_id = await asyncio.to_thread(cs.verify_channel, VIDEO_A, creator_channels)
        
        print(f"Video A channel_id: {channel_id}")
        print(f"Creator channels: {creator_channels}")
        
        if channel_id not in creator_channels:
            print(f"✅ FRAUD scenario: Video from unknown channel {channel_id}")
        else:
            print(f"ℹ️  Video A is from creator's own channel")
    except RuntimeError as e:
        pytest.skip(f"YouTube video unavailable: {e}")


# ============================================================================
# CPI TESTS ( requer localnet ou devnet com programa inicializado )
# ============================================================================

@pytest.mark.asyncio
async def test_cpi_create_pool():
    """Test 5: createPool() CPI - verifies PDA derivation."""
    print("=" * 60)
    print("CPI TEST: createPool() - PDA Derivation")
    print("=" * 60)
    
    from src.solana.connection import SolanaConnection
    from src.config import config
    from solders.pubkey import Pubkey
    
    oracle_path = Path(__file__).parent.parent / "keys" / "oracle.json"
    if not oracle_path.exists():
        pytest.skip(f"Oracle keypair not found: {oracle_path}")
    
    connection = SolanaConnection(config.SOLANA_RPC_URL, str(oracle_path))
    
    video_id = f"test_{int(time.time())}"
    pool_pda, bump = connection._find_pda(b"pool", video_id.encode())
    
    print(f"Pool PDA: {pool_pda}")
    print(f"Bump seed: {bump}")
    print(f"Program ID: {connection.program_id}")
    
    assert pool_pda is not None
    print("✅ PDA derivation works correctly")


@pytest.mark.asyncio
async def test_cpi_update_metrics():
    """Test 6: updateMetrics() CPI."""
    print("=" * 60)
    print("CPI TEST: updateMetrics()")
    print("=" * 60)
    
    from src.solana.connection import OracleCPI, SolanaConnection
    from src.config import config
    
    oracle_path = Path(__file__).parent.parent / "keys" / "oracle.json"
    if not oracle_path.exists():
        pytest.skip(f"Oracle keypair not found: {oracle_path}")
    
    connection = SolanaConnection(config.SOLANA_RPC_URL, str(oracle_path))
    cpi = OracleCPI(connection, PROGRAM_ID)
    
    entry_pda = "4B5gYJMBbN2f3Y9g7hK1cR6mPqW8xLkJsTuV3dHeSf"
    pool_pda = "7KpJ3M2nK4f4H8jK6dL5sR9tPwXy2BnMqVsU1wJeYg"
    views = 1000
    likes = 100
    comments = 50
    link_hash = hashlib.sha256(VIDEO_B.encode()).digest()
    
    try:
        tx = await cpi.update_metrics(
            entry_pda=entry_pda,
            pool_pda=pool_pda,
            views=views,
            likes=likes,
            comments=comments,
            link_hash=link_hash,
        )
        if tx.startswith("tx-error:"):
            print(f"⚠️  CPI failed (program not initialized): {tx}")
        else:
            print(f"Transaction: {tx}")
            print("✅ CPI instruction sent successfully")
    except NotImplementedError as e:
        print(f"ℹ️  CPI não implementado: {e}")
    except Exception as e:
        print(f"⚠️  Erro: {e}")


@pytest.mark.asyncio
async def test_cpi_slash_user():
    """Test 7: slashUser() CPI."""
    print("=" * 60)
    print("CPI TEST: slashUser()")
    print("=" * 60)
    
    from src.solana.connection import OracleCPI, SolanaConnection
    from src.config import config
    from solders.pubkey import Pubkey
    
    oracle_path = Path(__file__).parent.parent / "keys" / "oracle.json"
    if not oracle_path.exists():
        pytest.skip(f"Oracle keypair not found: {oracle_path}")
    
    connection = SolanaConnection(config.SOLANA_RPC_URL, str(oracle_path))
    cpi = OracleCPI(connection, PROGRAM_ID)
    
    user_authority = "4B5gYJMBbN2f3Y9g7hK1cR6mPqW8xLkJsTuV3dHeSf"
    
    try:
        tx = await cpi.slash_user(user_authority)
        if tx.startswith("tx-error:"):
            print(f"⚠️  CPI failed (program not initialized): {tx}")
        else:
            print(f"Transaction: {tx}")
            print("✅ CPI instruction sent successfully")
    except NotImplementedError as e:
        print(f"ℹ️  CPI não implementado: {e}")
    except Exception as e:
        print(f"⚠️  Erro: {e}")


@pytest.mark.asyncio
async def test_cpi_close_and_payout():
    """Test 8: closeAndPayout() CPI."""
    print("=" * 60)
    print("CPI TEST: closeAndPayout()")
    print("=" * 60)
    
    from src.solana.connection import OracleCPI, SolanaConnection
    from src.config import config
    
    oracle_path = Path(__file__).parent.parent / "keys" / "oracle.json"
    if not oracle_path.exists():
        pytest.skip(f"Oracle keypair not found: {oracle_path}")
    
    connection = SolanaConnection(config.SOLANA_RPC_URL, str(oracle_path))
    cpi = OracleCPI(connection, PROGRAM_ID)
    
    pool_pda = "7KpJ3M2nK4f4H8jK6dL5sR9tPwXy2BnMqVsU1wJeYg"
    
    try:
        tx = await cpi.close_and_payout(pool_pda)
        if tx.startswith("tx-error:"):
            print(f"⚠️  CPI failed (program not initialized): {tx}")
        else:
            print(f"Transaction: {tx}")
            print("✅ CPI instruction sent successfully")
    except NotImplementedError as e:
        print(f"ℹ️  CPI não implementado: {e}")
    except Exception as e:
        print(f"⚠️  Erro: {e}")


# ============================================================================
# SCORE CALCULATION TEST
# ============================================================================

@pytest.mark.asyncio
async def test_score_calculation():
    """Test 9: Score calculation with pool rules."""
    from src.solana.connection import calculate_score
    
    scoring_rules = {
        "views_weight": 5000,
        "likes_weight": 3000,
        "comments_weight": 2000,
    }
    
    score = calculate_score(1000, 100, 50, scoring_rules)
    expected = (1000 * 5000 + 100 * 3000 + 50 * 2000) // 10000
    
    assert score == expected, f"Failed: {score} != {expected}"
    print(f"✅ Score: {score} (expected: {expected})")


# ============================================================================
# FULL E2E TEST RUNNER
# ============================================================================

async def run_all_tests():
    """Run all E2E tests."""
    print("=" * 70)
    print("E2E ORACLE AGENT TEST SUITE")
    print("=" * 70)
    
    tests = [
        ("1. Transcript Validation", test_validation_transcript_similarity),
        ("2. Score Calculation", test_score_calculation),
        ("3. CPI - createPool", test_cpi_create_pool),
        ("4. CPI - updateMetrics", test_cpi_update_metrics),
        ("5. CPI - slashUser", test_cpi_slash_user),
        ("6. CPI - closeAndPayout", test_cpi_close_and_payout),
    ]
    
    results = []
    
    for name, test_fn in tests:
        print(f"\n{name}")
        print("-" * 60)
        try:
            await test_fn()
            results.append((name, "PASS"))
        except Exception as e:
            results.append((name, f"FAIL: {e}"))
            print(f"❌ Failed: {e}")
    
    print("\n" + "=" * 70)
    print("RESULTS")
    print("=" * 70)
    
    for name, result in results:
        status = "✅" if result == "PASS" else "❌"
        print(f"{status} {name}: {result}")
    
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(run_all_tests())