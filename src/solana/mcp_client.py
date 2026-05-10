"""Solana MCP Client for Oracle Agent."""
import asyncio
import hashlib
from typing import Optional
import httpx
from solders.pubkey import Pubkey

from ..config import config


class SolanaMCPClient:
    """Cliente para interagir com Solana via RPC HTTP.
    
    Based on llms-full.txt RPC API:
    - getAccountInfo
    - getProgramAccounts
    
    Também suporta MCP remoto quando configurado.
    """
    
    def __init__(
        self,
        rpc_url: str = "https://api.devnet.solana.com",
        program_id: str = None
    ):
        self.rpc_url = rpc_url
        self.program_id = program_id or config.PROGRAM_ID
        
    async def _rpc_call(self, method: str, params: list) -> dict:
        """Executa JSON-RPC call via HTTP."""
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                self.rpc_url,
                json={
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": method,
                    "params": params
                }
            )
            result = response.json()
            if "error" in result:
                raise RuntimeError(f"RPC Error: {result['error']}")
            return result.get("result", {})
    
    async def get_account_info(
        self,
        pubkey: str,
        encoding: str = "base64"
    ) -> dict:
        """Busca info de uma account.
        
        Based on llms-full.txt: getAccountInfo RPC
        """
        return await self._rpc_call("getAccountInfo", [pubkey, {"encoding": encoding}])
    
    async def get_program_accounts(
        self,
        program_id: str = None,
        encoding: str = "base64"
    ) -> list[dict]:
        """Busca todas as accounts de um programa.
        
        Based on llms-full.txt: getProgramAccounts RPC
        """
        pid = program_id or self.program_id
        return await self._rpc_call("getProgramAccounts", [pid, {"encoding": encoding}])
    
    async def get_transaction(self, tx_sig: str) -> dict:
        """Busca uma transação."""
        return await self._rpc_call("getTransaction", [tx_sig, {"encoding": "base64"}])
    
    async def get_latest_blockhash(self) -> dict:
        """Busca o último blockhash."""
        return await self._rpc_call("getLatestBlockhash", [{"commitment": "confirmed"}])
    
    # === Funções de Alto Nível ===
    
    async def get_global_config(self) -> dict:
        """Busca GlobalConfig."""
        pda, _ = self._find_pda(b"global_config_v1")
        return await self.get_account_info(pda)
    
    async def get_active_pools(self) -> list[dict]:
        """Busca pools com status = Open e não expiradas.

        Returns list of VideoPool accounts com status==0 (Open) e expiryTimestamp > now
        Decodes Borsh-serialized data from blockchain.
        """
        import base64
        import time
        import struct
        from loguru import logger

        accounts = await self.get_program_accounts()
        active_pools = []
        current_timestamp = int(time.time())

        logger.debug(f"[get_active_pools] Total accounts from RPC: {len(accounts)}")

        for account in accounts:
            pool_pubkey = account.get("pubkey", "unknown")
            try:
                # RPC returns account data in base64
                data_b64 = account.get("account", {}).get("data", [None])[0]
                if not data_b64:
                    continue

                # Decode from base64
                data = base64.b64decode(data_b64)
                if len(data) < 100:
                    logger.debug(f"[{pool_pubkey}] Data too short: {len(data)} bytes")
                    continue

                offset = 0

                # Skip Anchor discriminator (8 bytes)
                offset = 8

                # creator: PublicKey (32 bytes)
                creator_bytes = data[offset:offset+32]
                creator = str(Pubkey(creator_bytes))
                offset += 32

                # original_video_id: String (4-byte length + variable data)
                str_len_bytes = data[offset:offset+4]
                str_len = struct.unpack('<I', str_len_bytes)[0]
                video_id = ""
                try:
                    video_id = data[offset+4:offset+4+str_len].decode('utf-8')
                except:
                    video_id = "<decode_error>"
                logger.debug(f"[{pool_pubkey}] video_id: {video_id} (len_bytes={list(str_len_bytes)}, len_value={str_len})")
                old_offset = offset
                offset += 4 + str_len
                logger.debug(f"[{pool_pubkey}] after video_id: offset {old_offset} -> {offset}")

                # prize_vault: PublicKey (32 bytes)
                offset += 32

                # prize_amount: u64 (8 bytes)
                offset += 8

                # scoring_rules: ScoringRules struct (3x u16 = 6 bytes, NOT 12!)
                offset += 6

                # status: PoolStatus enum (u8)
                if offset >= len(data):
                    logger.debug(f"[{pool_pubkey}] Not enough data for status (offset={offset}, len={len(data)})")
                    continue

                status = data[offset]
                logger.debug(f"[{pool_pubkey}] status={status}")
                offset += 1

                # participant_count: u32 (4 bytes)
                offset += 4

                # total_score: u64 (8 bytes)
                offset += 8

                # expiry_timestamp: i64 (8 bytes, SIGNED!)
                if offset + 8 > len(data):
                    logger.debug(f"[{pool_pubkey}] Not enough data for expiry_timestamp (offset={offset}, data_len={len(data)})")
                    continue

                expiry_timestamp = struct.unpack('<q', data[offset:offset+8])[0]  # lowercase 'q' for signed
                logger.debug(f"[{pool_pubkey}] expiry_timestamp={expiry_timestamp}, current={current_timestamp}")

                # Filter: only include Open pools (status == 0) that haven't expired
                if status == 0 and expiry_timestamp > current_timestamp:
                    logger.info(f"[{pool_pubkey}] ACTIVE POOL FOUND! status=0, expiry={expiry_timestamp}, creator={creator}")
                    active_pools.append({
                        "pubkey": pool_pubkey,
                        "pool_pda": pool_pubkey,  # Both formats for compatibility
                        "creator": creator,
                        "status": status,
                        "expiryTimestamp": expiry_timestamp,
                        "expiry_timestamp": expiry_timestamp,  # Both formats for compatibility
                    })
                else:
                    logger.debug(f"[{pool_pubkey}] Filtered out: status={status}, expired={expiry_timestamp <= current_timestamp}")
            except Exception as e:
                logger.debug(f"[{pool_pubkey}] Exception: {e}")
                continue

        logger.info(f"[get_active_pools] Found {len(active_pools)} active pools")
        return active_pools
    
    async def get_entries_for_pool(self, pool_pda: str) -> list[dict]:
        """Busca participant entries de uma pool específica.

        Deserializes ParticipantEntry accounts and filters by pool_pda.
        Returns list of entries with decoded fields: entry_pda, pool_pda, user, clip_link, score, claimed, etc.
        """
        import base64
        import struct
        from loguru import logger

        accounts = await self.get_program_accounts()
        entries = []

        for account in accounts:
            entry_pubkey = account.get("pubkey", "unknown")
            try:
                # RPC returns account data in base64
                data_b64 = account.get("account", {}).get("data", [None])[0]
                if not data_b64:
                    continue

                data = base64.b64decode(data_b64)
                if len(data) < 150:
                    logger.debug(f"[get_entries_for_pool] Entry {entry_pubkey}: data too short {len(data)} bytes")
                    continue

                offset = 0

                # Skip discriminator (8 bytes)
                offset = 8

                # pool_pda: PublicKey (32 bytes)
                entry_pool = str(Pubkey(data[offset:offset+32]))
                offset += 32

                # Skip to score field (other fields before it)
                # user: PublicKey (32 bytes)
                user_bytes = data[offset:offset+32]
                user = str(Pubkey(user_bytes))
                offset += 32

                # channel_id: String (4-byte length + UTF-8 data)
                ch_str_len = struct.unpack('<I', data[offset:offset+4])[0]
                offset += 4
                channel_id = ""
                if ch_str_len > 0 and ch_str_len < 1000:
                    try:
                        channel_id = data[offset:offset+ch_str_len].decode('utf-8')
                    except:
                        channel_id = "<decode_error>"
                offset += ch_str_len

                # clip_link: String (4-byte length + UTF-8 data)
                str_len = struct.unpack('<I', data[offset:offset+4])[0]
                offset += 4
                clip_link = ""
                if str_len > 0 and str_len < 1000:
                    try:
                        clip_link = data[offset:offset+str_len].decode('utf-8')
                    except:
                        clip_link = "<decode_error>"
                offset += str_len

                # Skip other fields to get to score
                # views: u64 (8 bytes)
                offset += 8
                # likes: u64 (8 bytes)
                offset += 8
                # comments: u64 (8 bytes)
                offset += 8

                # score: u64 (8 bytes)
                if offset + 8 > len(data):
                    logger.debug(f"[get_entries_for_pool] Entry {entry_pubkey}: not enough data for score")
                    continue

                score = struct.unpack('<Q', data[offset:offset+8])[0]
                offset += 8

                # claimed: bool (1 byte)
                claimed = offset < len(data) and data[offset] == 1
                offset += 1

                # Only include entries from this pool
                if entry_pool == pool_pda:
                    entries.append({
                        "entry_pda": entry_pubkey,
                        "pubkey": entry_pubkey,
                        "pool_pda": entry_pool,
                        "user": user,
                        "channel_id": channel_id,
                        "clip_link": clip_link,
                        "score": score,
                        "claimed": claimed,
                    })

            except Exception as e:
                logger.debug(f"[get_entries_for_pool] Entry {entry_pubkey}: {e}")
                continue

        logger.debug(f"[get_entries_for_pool] Found {len(entries)} entries for pool {pool_pda}")
        return entries
    
    async def get_user_profile(self, authority: str) -> dict:
        """Busca UserProfile de um usuário.

        Args:
            authority: wallet address do usuário

        Returns:
            dict com campos: authority, channelIds, is_banned, bump
        """
        import base64
        import struct
        from loguru import logger

        authority_bytes = bytes(Pubkey.from_string(authority))
        pda, _ = self._find_pda(b"user_profile", authority_bytes)
        logger.debug(f"[get_user_profile] authority={authority}, pda={pda}")

        # Get raw account data
        account_data = await self.get_account_info(pda)
        if not account_data or "data" not in account_data or not account_data["data"]:
            logger.debug(f"[get_user_profile] No data found for {pda}")
            return {}

        # Parse Borsh data
        data_b64 = account_data.get("data", [None])[0]
        if not data_b64:
            return {}

        try:
            data = base64.b64decode(data_b64)
        except Exception as e:
            logger.error(f"[get_user_profile] Failed to decode base64: {e}")
            return {}

        if len(data) < 50:
            logger.debug(f"[get_user_profile] Data too short: {len(data)} bytes")
            return {}

        offset = 0

        # Skip discriminator (8 bytes)
        offset = 8

        # authority: PublicKey (32 bytes)
        authority_parsed = str(Pubkey(data[offset:offset+32]))
        offset += 32

        # channel_ids: Vec<String> (u32 length + variable data)
        vec_len = struct.unpack('<I', data[offset:offset+4])[0]
        offset += 4

        channel_ids = []
        for i in range(vec_len):
            if offset + 4 > len(data):
                break
            str_len = struct.unpack('<I', data[offset:offset+4])[0]
            offset += 4
            if offset + str_len <= len(data):
                channel_id = data[offset:offset+str_len].decode('utf-8', errors='ignore')
                channel_ids.append(channel_id)
                offset += str_len

        # is_banned: bool (1 byte)
        is_banned = offset < len(data) and data[offset] == 1
        offset += 1

        # bump: u8 (1 byte)
        bump = data[offset] if offset < len(data) else 0

        logger.debug(f"[get_user_profile] Parsed: authority={authority_parsed}, channels={len(channel_ids)}, banned={is_banned}")

        return {
            "authority": authority_parsed,
            "channelIds": channel_ids,
            "is_banned": is_banned,
            "bump": bump,
        }

    def find_user_profile_pda(self, authority: str) -> tuple[str, int]:
        """Calcula PDA do UserProfile.

        Args:
            authority: wallet address do usuário

        Returns:
            (pda_address, bump_seed)
        """
        authority_bytes = bytes(Pubkey.from_string(authority))
        return self._find_pda(b"user_profile", authority_bytes)
    
    async def get_stake_account(self, authority: str) -> dict:
        """Busca StakeAccount de um usuário.
        
        Args:
            authority: wallet address do usuário
        """
        pda, _ = self._find_pda(b"stake", authority.encode())
        return await self.get_account_info(pda)
    
    # === CPI Functions ===
    # Estas precisam ser implementadas via invoke_signed quando MCP disponível
    
    async def update_metrics(
        self,
        entry_pda: str,
        pool_pda: str,
        views: int,
        likes: int,
        comments: int,
        link_hash: bytes,
        oracle_keypair: "Keypair" = None,
    ) -> str:
        """Executa update_metrics instruction via CPI.
        
        Args:
            entry_pda: ParticipantEntry address
            pool_pda: VideoPool address
            views: u64
            likes: u64
            comments: u64
            link_hash: [u8; 32] - hash do clip_link
            oracle_keypair: keypair do oracle (para signing)
        
        Returns:
            Transaction signature
        """
        # TODO: Implementar via anchorpy ou invoke_signed do MCP
        raise NotImplementedError("CPI implementation pending")
    
    async def slash_user(
        self,
        user_authority: str,
        oracle_keypair: "Keypair" = None,
    ) -> str:
        """Executa slash_user instruction via CPI.
        
        Args:
            user_authority: wallet do usuário a banir
            oracle_keypair: keypair do oracle (para signing)
        
        Returns:
            Transaction signature
        """
        # TODO: Implementar via anchorpy ou invoke_signed do MCP
        raise NotImplementedError("CPI implementation pending")
    
    async def close_and_payout(
        self,
        pool_pda: str,
        video_id: str,
        oracle_keypair: "Keypair" = None,
    ) -> str:
        """Executa close_and_payout instruction via CPI.
        
        Args:
            pool_pda: VideoPool address
            video_id: ID do vídeo original
            oracle_keypair: keypair do oracle (para signing)
        
        Returns:
            Transaction signature
        """
        # TODO: Implementar via anchorpy ou invoke_signed do MCP
        raise NotImplementedError("CPI implementation pending")
    
    # === Helpers ===
    
    def _find_pda(self, seed: bytes, *extra_seeds) -> tuple[str, int]:
        """Calcula PDA com bump seed.
        
        Based on llms-full.txt: PublicKey.findProgramAddressSync()
        
        Returns:
            (pda_address, bump_seed)
        """
        program_id = Pubkey.from_string(self.program_id)
        all_seeds = [seed] + list(extra_seeds)
        pda, bump = Pubkey.find_program_address(all_seeds, program_id)
        return str(pda), bump
    
    def find_pda_sync(self, seed: bytes, *extra_seeds) -> tuple[str, int]:
        """Versão síncrona de _find_pda."""
        return self._find_pda(seed, *extra_seeds)
    
    @staticmethod
    def compute_link_hash(clip_link: str) -> bytes:
        """Calcula hash de 32 bytes para clip_link.
        
        Usado para derivar ParticipantEntry PDA.
        """
        return hashlib.sha256(clip_link.encode()).digest()


class SolanaMCPClientLocal:
    """MCP Client para usar com servidor MCP local/remoto.
    
    Esta classe é um wrapper que pode usar o MCP server
    quando disponível via opencode.json.
    """
    
    def __init__(self, mcp_server_name: str = "solana"):
        self.mcp_server_name = mcp_server_name
        self.rpc_url = "https://api.devnet.solana.com"
        self.program_id = config.PROGRAM_ID
    
    async def get_account_info(self, pubkey: str) -> dict:
        """Busca info via MCP.
        
        Nota: Requer MCP configurado no opencode.json
        """
        # Fallback para RPC direto se MCP não disponível
        client = SolanaMCPClient(self.rpc_url, self.program_id)
        return await client.get_account_info(pubkey)
    
    async def get_program_accounts(self) -> list[dict]:
        """Busca accounts via MCP."""
        client = SolanaMCPClient(self.rpc_url, self.program_id)
        return await client.get_program_accounts()
    
    async def get_active_pools(self) -> list[dict]:
        """Busca pools ativas via MCP."""
        client = SolanaMCPClient(self.rpc_url, self.program_id)
        return await client.get_active_pools()


# Alias para compatibilidade
SolanaConnection = SolanaMCPClient