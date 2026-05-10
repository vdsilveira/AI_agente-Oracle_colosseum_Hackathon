"""Solana connection and CPI instructions."""

import asyncio
import hashlib
from pathlib import Path
from typing import Optional
from solders.pubkey import Pubkey
from solders.keypair import Keypair
from solders.instruction import Instruction, AccountMeta
from solders.transaction import Transaction
from solders.message import Message
from solana.rpc.api import Client

from .mcp_client import SolanaMCPClient
from ..config import config


PROGRAM_ID = config.PROGRAM_ID


class SolanaConnection:
    """Solana connection manager."""

    def __init__(self, rpc_url: str, keypair_path: str = None):
        self.rpc_url = rpc_url
        self.client = Client(rpc_url)
        self.keypair = self._load_keypair(keypair_path)
        self.mcp_client = SolanaMCPClient(rpc_url, config.PROGRAM_ID)
        self.program_id = Pubkey.from_string(config.PROGRAM_ID)

    def _load_keypair(self, path: str = None) -> Keypair:
        """Load oracle keypair from config environment variables."""
        private_key = config.ORACLE_PRIVATE_KEY
        if not private_key:
            raise ValueError("ORACLE_PRIVATE_KEY is required in .env")
        
        try:
            return Keypair.from_base58_string(private_key)
        except Exception as e:
            raise ValueError(f"Invalid private key: {e}")

    @property
    def public_key(self):
        """Get oracle public key."""
        return self.keypair.pubkey()

    @property
    def oracle_pubkey(self) -> Pubkey:
        """Get oracle public key as Pubkey."""
        return self.keypair.pubkey()

    def _find_pda(self, *seeds) -> tuple[Pubkey, int]:
        """Find PDA with bump seed."""
        return Pubkey.find_program_address(list(seeds), self.program_id)

    async def get_global_config(self) -> dict:
        """Get GlobalConfig account."""
        pda, _ = self._find_pda(b"global_config_v1")
        return await self.mcp_client.get_account_info(str(pda))

    async def get_account_info(self, pubkey: str) -> dict:
        """Get account info."""
        return await self.mcp_client.get_account_info(pubkey)

    async def get_program_accounts(self, program_id: str = None) -> list:
        """Get all accounts owned by program."""
        return await self.mcp_client.get_program_accounts(program_id)

    async def get_active_pools(self) -> list:
        """Get active (Open) pools."""
        return await self.mcp_client.get_active_pools()

    async def get_entries_for_pool(self, pool_pda: str) -> list:
        """Get participant entries for a pool."""
        return await self.mcp_client.get_entries_for_pool(pool_pda)

    async def get_entry_pda(self, pool_pda: str, clip_link: str) -> tuple[str, int]:
        """Get ParticipantEntry PDA for a clip link."""
        link_hash = hashlib.sha256(clip_link.encode()).digest()
        pool_bytes = Pubkey.from_string(pool_pda).to_bytes()
        return self._find_pda(b"entry", pool_bytes, link_hash)

    async def get_user_profile_pda(self, authority: str) -> tuple[str, int]:
        """Get UserProfile PDA."""
        authority_bytes = bytes(Pubkey.from_string(authority))
        pda, bump = self._find_pda(b"user_profile", authority_bytes)
        return pda, bump

    async def get_stake_account_pda(self, authority: str) -> tuple[str, int]:
        """Get StakeAccount PDA."""
        authority_bytes = bytes(Pubkey.from_string(authority))
        pda, bump = self._find_pda(b"stake", authority_bytes)
        return pda, bump

    async def get_creator_channels(self, creator_authority: str) -> list[str]:
        """Busca channel_ids do UserProfile do criador on-chain.
        
        O créateur deve ter chamado initializeUser() antes de criar a pool.
        O oracle lê os canais registrados no UserProfile para validar entries.
        """
        from ..config import config
        try:
            profile = await self.get_user_profile(creator_authority)
            return profile.get("channelIds", [])
        except Exception as e:
            from loguru import logger
            logger.warning(f"Failed to get creator channels for {creator_authority}: {e}")
            return []

    async def get_user_profile(self, authority: str) -> dict:
        """Busca UserProfile de um usuário (decodificado via Borsh).
        
        Args:
            authority: wallet address do usuário
        
        Returns:
            dict com campos: authority, channelIds, is_banned, bump
        """
        return await self.mcp_client.get_user_profile(authority)

    async def get_treasury(self) -> str:
        """Busca treasury address do GlobalConfig."""
        try:
            config = await self.get_global_config()
            return config.get("treasury", "")
        except Exception:
            return ""

    async def get_pool_creator(self, pool_pda: str) -> str:
        """Busca creator de uma pool."""
        try:
            pool = await self.get_account_info(pool_pda)
            return pool.get("creator", "")
        except Exception:
            return ""


class OracleCPI:
    """Execute CPI instructions as oracle using anchorpy."""

    def __init__(self, connection: SolanaConnection, program_id: str = None):
        self.connection = connection
        self.program_id = program_id or PROGRAM_ID
        self._program = None

    async def _get_program(self):
        """Lazy load anchorpy program."""
        if self._program is None:
            try:
                from anchorpy import Program, Provider, Idl
                client = Client(self.connection.rpc_url)
                from anchorpy.wallet import Wallet
                wallet = Wallet(self.connection.keypair)
                provider = Provider(client, wallet)
                idl = await Idl.fetch(self.connection.program_id, provider)
                from solders.pubkey import Pubkey
                program_pubkey = Pubkey.from_string(self.program_id)
                self._program = Program(idl, program_pubkey, provider)
            except ImportError:
                return None
        return self._program

    async def update_metrics(
        self,
        entry_pda: str,
        pool_pda: str,
        views: int,
        likes: int,
        comments: int,
        link_hash: Optional[bytes] = None,
    ) -> str:
        """Call update_metrics instruction.
        
        Args:
            entry_pda: ParticipantEntry address
            pool_pda: VideoPool address
            views: view count
            likes: like count
            comments: comment count
            link_hash: 32-byte hash of clip_link
        
        Returns:
            Transaction signature
        """
        program = await self._get_program()
        if program is None:
            return await self._update_metrics_rpc(
                entry_pda, pool_pda, views, likes, comments, link_hash
            )
        
        conn = self.connection
        entry = Pubkey.from_string(entry_pda)
        pool = Pubkey.from_string(pool_pda)
        
        if link_hash is None:
            link_hash = b"\x00" * 32
        
        config_pda, _ = conn._find_pda(b"global_config_v1")
        
        tx = program.transaction["update_metrics"](
            views,
            likes,
            comments,
            list(link_hash),
            accounts={
                "entry": entry,
                "pool": pool,
                "config": config_pda,
                "oracle": conn.oracle_pubkey,
            }
        )
        
        tx_sig = await conn.client.send_transaction(tx, conn.keypair)
        return str(tx_sig.value)

    async def _update_metrics_rpc(
        self,
        entry_pda: str,
        pool_pda: str,
        views: int,
        likes: int,
        comments: int,
        link_hash: Optional[bytes] = None,
    ) -> str:
        """Fallback update_metrics via RPC instruction."""
        import base64
        from solders.instruction import Instruction, AccountMeta
        
        if link_hash is None:
            link_hash = b"\x00" * 32
        
        program_id = Pubkey.from_string(self.program_id)
        entry = Pubkey.from_string(entry_pda)
        pool = Pubkey.from_string(pool_pda)
        config_pda, _ = Pubkey.find_program_address([b"global_config_v1"], program_id)
        
        # Anchor 8-byte discriminator: sha256("global:update_metrics")[:8]
        data = bytes([79, 114, 128, 135, 148, 137, 172, 185])
        data += views.to_bytes(8, "little")
        data += likes.to_bytes(8, "little")
        data += comments.to_bytes(8, "little")
        data += link_hash
        
        instruction = Instruction(
            program_id=program_id,
            data=data,
            accounts=[
                AccountMeta(entry, False, True),
                AccountMeta(pool, False, True),
                AccountMeta(config_pda, False, False),
                AccountMeta(self.connection.oracle_pubkey, True, False),
            ]
        )
        
        try:
            blockhash = self.connection.client.get_latest_blockhash().value.blockhash
            msg = Message.new_with_blockhash(
                instructions=[instruction],
                payer=self.connection.oracle_pubkey,
                blockhash=blockhash,
            )
            tx = Transaction.new_unsigned(msg)
            tx.sign([self.connection.keypair], blockhash)
            result = await self.connection.client.send_transaction(tx)
            return str(result.value)
        except Exception as e:
            return f"tx-error: {e}"

    async def slash_user(
        self,
        user_authority: str,
    ) -> str:
        """Call slash_user instruction (for fraud detection).
        
        Args:
            user_authority: Wallet address of user to ban
        
        Returns:
            Transaction signature
        """
        program = await self._get_program()
        if program is None:
            return await self._slash_user_rpc(user_authority)
        
        conn = self.connection
        user_authority_pk = Pubkey.from_string(user_authority)
        
        user_profile, _ = Pubkey.find_program_address(
            [b"user_profile", user_authority_pk.to_bytes()],
            conn.program_id
        )
        stake_account, _ = Pubkey.find_program_address(
            [b"stake", user_authority_pk.to_bytes()],
            conn.program_id
        )
        
        config_pda, _ = conn._find_pda(b"global_config_v1")
        
        global_config = await conn.get_global_config()
        treasury = Pubkey.from_string(global_config.get("treasury", ""))
        
        tx = program.transaction["slash_user"](
            accounts={
                "config": config_pda,
                "user_profile": user_profile,
                "stake_account": stake_account,
                "treasury": treasury,
                "caller": conn.oracle_pubkey,
            }
        )
        
        tx_sig = await conn.client.send_transaction(tx, conn.keypair)
        return str(tx_sig.value)

    async def _slash_user_rpc(self, user_authority: str) -> str:
        """Fallback slash_user via RPC instruction."""
        from solders.instruction import Instruction, AccountMeta
        
        program_id = Pubkey.from_string(self.program_id)
        user_authority_pk = Pubkey.from_string(user_authority)
        
        user_profile, _ = Pubkey.find_program_address(
            [b"user_profile", user_authority_pk.to_bytes()],
            program_id
        )
        stake_account, _ = Pubkey.find_program_address(
            [b"stake", user_authority_pk.to_bytes()],
            program_id
        )
        
        config, _ = Pubkey.find_program_address([b"global_config_v1"], program_id)
        global_config = await self.connection.get_global_config()
        treasury = Pubkey.from_string(global_config.get("treasury", ""))
        
        # Anchor 8-byte discriminator: sha256("global:slash_user")[:8]
        data = bytes([208, 190, 26, 101, 212, 59, 107, 8])
        
        instruction = Instruction(
            program_id=program_id,
            data=data,
            accounts=[
                AccountMeta(config, False, False),
                AccountMeta(user_profile, False, True),
                AccountMeta(stake_account, False, True),
                AccountMeta(treasury, False, True),
                AccountMeta(self.connection.oracle_pubkey, True, False),
            ]
        )
        
        try:
            blockhash = self.connection.client.get_latest_blockhash().value.blockhash
            msg = Message.new_with_blockhash(
                instructions=[instruction],
                payer=self.connection.oracle_pubkey,
                blockhash=blockhash,
            )
            tx = Transaction.new_unsigned(msg)
            tx.sign([self.connection.keypair], blockhash)
            result = await self.connection.client.send_transaction(tx)
            return str(result.value)
        except Exception as e:
            return f"tx-error: {e}"

    async def close_and_payout(
        self,
        pool_pda: str,
    ) -> str:
        """Call close_and_payout instruction.
        
        Args:
            pool_pda: VideoPool address
        
        Returns:
            Transaction signature
        """
        program = await self._get_program()
        if program is None:
            return await self._close_and_payout_rpc(pool_pda)
        
        conn = self.connection
        pool = Pubkey.from_string(pool_pda)
        
        pool_data = await conn.get_account_info(pool_pda)
        creator = Pubkey.from_string(pool_data.get("creator", ""))
        
        vault, _ = Pubkey.find_program_address(
            [b"vault", pool.to_bytes()],
            conn.program_id
        )
        
        config_pda, _ = conn._find_pda(b"global_config_v1")
        
        global_config = await conn.get_global_config()
        treasury = Pubkey.from_string(global_config.get("treasury", ""))
        
        tx = program.transaction["close_and_payout"](
            accounts={
                "pool": pool,
                "prize_vault": vault,
                "creator": creator,
                "caller": conn.oracle_pubkey,
                "config": config_pda,
                "treasury": treasury,
                "system_program": Pubkey.from_string("11111111111111111111111111111111"),
            }
        )
        
        tx_sig = await conn.client.send_transaction(tx, conn.keypair)
        return str(tx_sig.value)

    async def _close_and_payout_rpc(self, pool_pda: str) -> str:
        """Fallback close_and_payout via RPC instruction."""
        from solders.instruction import Instruction, AccountMeta
        
        program_id = Pubkey.from_string(self.program_id)
        pool = Pubkey.from_string(pool_pda)
        
        pool_data = await self.connection.get_account_info(pool_pda)
        creator = Pubkey.from_string(pool_data.get("creator", ""))
        
        vault, _ = Pubkey.find_program_address(
            [b"vault", pool.to_bytes()],
            program_id
        )
        
        config, _ = Pubkey.find_program_address([b"global_config_v1"], program_id)
        global_config = await self.connection.get_global_config()
        treasury = Pubkey.from_string(global_config.get("treasury", ""))
        
        # Anchor 8-byte discriminator: sha256("global:close_and_payout")[:8]
        data = bytes([146, 191, 147, 126, 83, 78, 191, 118])
        
        instruction = Instruction(
            program_id=program_id,
            data=data,
            accounts=[
                AccountMeta(pool, False, True),
                AccountMeta(vault, False, True),
                AccountMeta(creator, False, True),
                AccountMeta(self.connection.oracle_pubkey, True, True),
                AccountMeta(config, False, False),
                AccountMeta(treasury, False, True),
                AccountMeta(Pubkey.from_string("11111111111111111111111111111111"), False, False),
            ]
        )
        
        try:
            blockhash = self.connection.client.get_latest_blockhash().value.blockhash
            msg = Message.new_with_blockhash(
                instructions=[instruction],
                payer=self.connection.oracle_pubkey,
                blockhash=blockhash,
            )
            tx = Transaction.new_unsigned(msg)
            tx.sign([self.connection.keypair], blockhash)
            result = await self.connection.client.send_transaction(tx)
            return str(result.value)
        except Exception as e:
            return f"tx-error: {e}"


def calculate_score(
    views: int,
    likes: int,
    comments: int,
    scoring_rules: dict,
) -> int:
    """Calculate weighted score using pool's scoring rules.
    
    scoring_rules:
    - views_weight: u16 (ex: 5000 = 50%)
    - likes_weight: u16 (ex: 3000 = 30%)
    - comments_weight: u16 (ex: 2000 = 20%)
    
    SCORE_BASE = 10_000 (100%)
    """
    views_weight = scoring_rules.get("views_weight", 5000)
    likes_weight = scoring_rules.get("likes_weight", 3000)
    comments_weight = scoring_rules.get("comments_weight", 2000)
    
    score = (
        (views * views_weight) +
        (likes * likes_weight) +
        (comments * comments_weight)
    ) // 10000
    
    return score


async def create_oracle_connection(
    rpc_url: str = "https://api.devnet.solana.com",
    keypair_path: str = None,
) -> SolanaConnection:
    """Create OracleConnection with validation."""
    return SolanaConnection(rpc_url, keypair_path)


async def create_oracle_cpi(connection: SolanaConnection) -> OracleCPI:
    """Create OracleCPI instance."""
    return OracleCPI(connection)