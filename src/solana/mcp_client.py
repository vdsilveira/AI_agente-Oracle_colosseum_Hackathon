"""Solana MCP Client for Oracle Agent."""
import asyncio
import hashlib
from typing import Optional
import httpx
from solders.pubkey import Pubkey


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
        program_id: str = "4RAbxbEVCsYaaK3WR8r7eYwrofTJ7yqdZ3hqSYRLPfT4"
    ):
        self.rpc_url = rpc_url
        self.program_id = program_id
        
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
        """Busca pools com status = Open.
        
        Returns list of VideoPool accounts com status==0 (Open)
        """
        accounts = await self.get_program_accounts()
        return [a for a in accounts if a.get("status") == 0]
    
    async def get_entries_for_pool(self, pool_pda: str) -> list[dict]:
        """Busca participant entries de uma pool específica.
        
        Returns list of ParticipantEntry accounts para uma pool
        """
        accounts = await self.get_program_accounts()
        return [a for a in accounts if a.get("pool") == pool_pda]
    
    async def get_user_profile(self, authority: str) -> dict:
        """Busca UserProfile de um usuário.
        
        Args:
            authority: wallet address do usuário
        
        Returns:
            dict com campos: authority, channel_ids, is_banned, bump
            O servidor MCP faz o decode Borsh automaticamente.
        """
        pda, _ = self._find_pda(b"user_profile", authority.encode())
        return await self.get_account_info(pda)

    def find_user_profile_pda(self, authority: str) -> tuple[str, int]:
        """Calcula PDA do UserProfile.
        
        Args:
            authority: wallet address do usuário
        
        Returns:
            (pda_address, bump_seed)
        """
        return self._find_pda(b"user_profile", authority.encode())
    
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
        self.program_id = "4RAbxbEVCsYaaK3WR8r7eYwrofTJ7yqdZ3hqSYRLPfT4"
    
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