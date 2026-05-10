"""
Backfill script: reads all pools and entries from Solana blockchain
and populates the core-api database via HTTP endpoints.

Usage:
    python -m scripts.backfill_db

Requires CORE_API_URL env var (default: http://localhost:8001/api/v1)
"""
import asyncio
import base64
import hashlib
import os
import struct
import time
from datetime import datetime, timezone

import httpx
from dotenv import load_dotenv
from loguru import logger
from solders.pubkey import Pubkey

load_dotenv()

SOLANA_RPC_URL = os.getenv("SOLANA_RPC_URL", "https://api.devnet.solana.com")
PROGRAM_ID = os.getenv("PROGRAM_ID", "J45dp2TMQXx5v5RDygsF3im7URJqu7QQ996V1kqXeNxN")
CORE_API_URL = os.getenv("CORE_API_URL", "http://localhost:8001/api/v1")
ORACLE_API_KEY = os.getenv("APP_API_KEY", "")

VIDEO_POOL_DISC = "PP5rDpEeLV6"
ENTRY_DISC = "cZazjaACyjF"


async def rpc_call(method: str, params: list) -> dict:
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            SOLANA_RPC_URL,
            json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params},
            timeout=30.0,
        )
        return resp.json()


async def fetch_all_pools() -> list[dict]:
    """Fetch ALL VideoPool accounts from chain (any status)."""
    raw = await rpc_call("getProgramAccounts", [
        PROGRAM_ID,
        {
            "encoding": "base64",
            "filters": [{"memcmp": {"offset": 0, "bytes": VIDEO_POOL_DISC}}],
        }
    ])

    accounts = raw.get("result", []) if isinstance(raw, dict) else []
    pools = []

    for item in accounts:
        try:
            pubkey = item.get("pubkey", "unknown")
            data_b64 = item.get("account", {}).get("data", [None])[0]
            if not data_b64:
                continue

            data = base64.b64decode(data_b64)
            offset = 8  # skip discriminator

            creator = str(Pubkey(data[offset:offset+32]))
            offset += 32

            str_len = struct.unpack('<I', data[offset:offset+4])[0]
            offset += 4
            video_id = data[offset:offset+str_len].decode('utf-8', errors='replace')
            offset += str_len

            offset += 32  # prize_vault
            prize_amount = struct.unpack('<Q', data[offset:offset+8])[0]
            offset += 8

            weights = struct.unpack('<HHH', data[offset:offset+6])
            offset += 6

            status = data[offset]
            offset += 1

            participant_count = struct.unpack('<I', data[offset:offset+4])[0]
            offset += 4

            total_score = struct.unpack('<Q', data[offset:offset+8])[0]
            offset += 8

            expiry_timestamp = struct.unpack('<q', data[offset:offset+8])[0]

            pools.append({
                "pda_address": pubkey,
                "creator_wallet": creator,
                "original_video_id": video_id,
                "prize_amount": prize_amount,
                "scoring_rules": {
                    "views_weight": weights[0],
                    "likes_weight": weights[1],
                    "comments_weight": weights[2],
                },
                "participant_count": participant_count,
                "total_score": total_score,
                "status": ["OPEN", "CLOSED", "DISTRIBUTED"][status] if status < 3 else "UNKNOWN",
                "expiry_timestamp": datetime.fromtimestamp(expiry_timestamp, tz=timezone.utc).isoformat(),
            })
        except Exception as e:
            logger.warning(f"Failed to decode pool {item.get('pubkey', '?')}: {e}")
            continue

    logger.info(f"Fetched {len(pools)} pools from chain")
    return pools


async def fetch_entries_for_pool(pool_pda: str) -> list[dict]:
    """Fetch all ParticipantEntry accounts for a pool."""
    raw = await rpc_call("getProgramAccounts", [
        PROGRAM_ID,
        {
            "encoding": "base64",
            "filters": [
                {"memcmp": {"offset": 0, "bytes": ENTRY_DISC}},
                {"memcmp": {"offset": 8, "bytes": pool_pda}},
            ],
        }
    ])

    accounts = raw.get("result", []) if isinstance(raw, dict) else []
    entries = []

    for item in accounts:
        try:
            pubkey = item.get("pubkey", "unknown")
            data_b64 = item.get("account", {}).get("data", [None])[0]
            if not data_b64:
                continue

            data = base64.b64decode(data_b64)
            offset = 8

            entry_pool = str(Pubkey(data[offset:offset+32]))
            offset += 32

            user = str(Pubkey(data[offset:offset+32]))
            offset += 32

            ch_str_len = struct.unpack('<I', data[offset:offset+4])[0]
            offset += 4
            channel_id = data[offset:offset+ch_str_len].decode('utf-8', errors='replace') if ch_str_len > 0 else ""
            offset += ch_str_len

            str_len = struct.unpack('<I', data[offset:offset+4])[0]
            offset += 4
            clip_link = data[offset:offset+str_len].decode('utf-8', errors='replace') if str_len > 0 else ""
            offset += str_len

            views = struct.unpack('<Q', data[offset:offset+8])[0]
            offset += 8
            likes = struct.unpack('<Q', data[offset:offset+8])[0]
            offset += 8
            comments = struct.unpack('<Q', data[offset:offset+8])[0]
            offset += 8

            score = struct.unpack('<Q', data[offset:offset+8])[0]
            offset += 8

            claimed = offset < len(data) and data[offset] == 1

            entries.append({
                "pda_address": pubkey,
                "pool_pda": entry_pool,
                "user_wallet": user,
                "channel_id": channel_id,
                "clip_link": clip_link,
                "views": views,
                "likes": likes,
                "comments": comments,
                "score": score,
                "claimed": claimed,
            })
        except Exception:
            continue

    return entries


async def sync_pool(client: httpx.AsyncClient, pool: dict) -> bool:
    """Send pool to core-api via POST /pools/sync."""
    headers = {"Content-Type": "application/json"}
    if ORACLE_API_KEY:
        headers["X-API-Key"] = ORACLE_API_KEY
    try:
        resp = await client.post(
            f"{CORE_API_URL}/pools/sync",
            json=pool,
            headers=headers,
            timeout=10.0,
        )
        if resp.status_code == 200:
            return True
        else:
            logger.warning(f"Pool sync failed ({resp.status_code}): {resp.text[:200]}")
            return False
    except Exception as e:
        logger.error(f"Pool sync error: {e}")
        return False


async def sync_entries(client: httpx.AsyncClient, entries: list[dict]) -> int:
    """Send entries to core-api via POST /entries/batch-sync."""
    if not entries:
        return 0
    headers = {"Content-Type": "application/json"}
    if ORACLE_API_KEY:
        headers["X-API-Key"] = ORACLE_API_KEY
    try:
        resp = await client.post(
            f"{CORE_API_URL}/entries/batch-sync",
            json={"entries": entries},
            headers=headers,
            timeout=30.0,
        )
        if resp.status_code == 200:
            data = resp.json()
            return data.get("upserted", 0)
        else:
            logger.warning(f"Entry batch-sync failed ({resp.status_code}): {resp.text[:200]}")
            return 0
    except Exception as e:
        logger.error(f"Entry batch-sync error: {e}")
        return 0


async def main():
    logger.info(f"Connecting to Solana RPC: {SOLANA_RPC_URL[:50]}...")
    logger.info(f"Core-API URL: {CORE_API_URL}")

    pools = await fetch_all_pools()
    logger.info(f"Found {len(pools)} pools total")

    async with httpx.AsyncClient() as client:
        for i, pool in enumerate(pools):
            logger.info(f"[{i+1}/{len(pools)}] Syncing pool {pool['pda_address'][:8]}... ({pool['status']})")

            ok = await sync_pool(client, pool)
            if not ok:
                logger.warning(f"  Skipping entries for pool due to sync failure")
                continue

            entries = await fetch_entries_for_pool(pool["pda_address"])
            logger.info(f"  Found {len(entries)} entries")

            upserted = await sync_entries(client, entries)
            logger.info(f"  Synced {upserted} entries")

            # Small delay to avoid hammering the API
            await asyncio.sleep(0.5)

    logger.success("Backfill complete!")


if __name__ == "__main__":
    asyncio.run(main())
