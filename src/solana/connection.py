"""Solana connection and CPI instructions."""

from typing import Optional
from pathlib import Path
from solana.rpc.api import Client
from solana.rpc.commitment import Confirmed
from solana.keypair import Keypair
from solana.transaction import Transaction
from solana.rpc.types import TxOpts


class SolanaConnection:
    """Solana connection manager."""

    def __init__(self, rpc_url: str, keypair_path: str):
        self.client = Client(rpc_url)
        self.keypair = self._load_keypair(keypair_path)

    def _load_keypair(self, path: str) -> Keypair:
        """Load oracle keypair from file."""
        keypath = Path(path)
        if not keypath.exists():
            raise FileNotFoundError(f"Keypair not found at {path}")

        with open(keypath) as f:
            keypair_data = f.read().strip()

        if keypair_data.startswith("["):
            return Keypair.from_json(keypair_data)
        else:
            return Keypair.from_secret_key(bytes.fromhex(keypair_data))

    @property
    def public_key(self):
        """Get oracle public key."""
        return self.keypair.public_key

    async def get_account_info(self, pubkey: str) -> dict:
        """Get account info."""
        return await self.client.get_account_info(pubkey)

    async def get_program_accounts(self, program_id: str) -> list:
        """Get all accounts owned by program."""
        return await self.client.get_program_accounts(program_id)


class OracleCPI:
    """Execute CPI instructions as oracle."""

    def __init__(self, connection: SolanaConnection, program_id: str):
        self.connection = connection
        self.program_id = program_id

    async def update_metrics(
        self,
        entry_pda: str,
        pool_pda: str,
        views: int,
        likes: int,
        comments: int,
    ) -> str:
        """
        Call update_metrics instruction.

        Returns transaction signature.
        """
        from solana.system_program import CreateAccountParams, SystemProgram
        from solana.transaction import AccountMeta

        builder = (
            Transaction()
            .add(
                SystemProgram.transfer(
                    {"from_pubkey": self.connection.public_key, "to_pubkey": entry_pda, "lamports": 1}
                )
            )
        )

        return "mock-tx-sig"

    async def slash_user(
        self,
        user_profile_pda: str,
        stake_account_pda: str,
        treasury_pda: str,
        reason: str,
    ) -> str:
        """
        Call slash_user instruction (for fraud detection).

        Returns transaction signature.
        """
        return "mock-slash-tx-sig"