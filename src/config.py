"""Configuration module for Oracle Agent."""

import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()


class Config:
    """Oracle Agent configuration."""

    JWT_TOKEN: str = os.getenv("JWT_TOKEN", "")
    SOLANA_RPC_URL: str = os.getenv("SOLANA_RPC_URL", "https://api.devnet.solana.com")
    ORACLE_KEYPAIR_PATH: str = os.getenv("ORACLE_KEYPAIR_PATH", "./keys/oracle.json")

    METRICS_API_URL: str = os.getenv("METRICS_API_URL", "https://backend-views-solana.onrender.com")
    METRICS_API_KEY: str = os.getenv("METRICS_API_KEY", "")

    TRANSCRIPT_MIN_SCORE: float = float(os.getenv("TRANSCRIPT_MIN_SCORE", "0.70"))
    FRAME_SIMILARITY_THRESHOLD: float = float(os.getenv("FRAME_SIMILARITY_THRESHOLD", "0.70"))
    FRAME_MIN_MATCHES: int = int(os.getenv("FRAME_MIN_MATCHES", "3"))
    FRAME_TOTAL_SAMPLES: int = int(os.getenv("FRAME_TOTAL_SAMPLES", "5"))

    POLL_INTERVAL_SECONDS: int = int(os.getenv("POLL_INTERVAL_SECONDS", "300"))

    DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite:///oracle.db")

    PROGRAM_ID: str = os.getenv("PROGRAM_ID", "")

    @classmethod
    def validate(cls) -> bool:
        """Validate required configuration."""
        if not cls.JWT_TOKEN:
            raise ValueError("JWT_TOKEN is required in .env")
        if not cls.SOLANA_RPC_URL:
            raise ValueError("SOLANA_RPC_URL is required in .env")
        if not cls.ORACLE_KEYPAIR_PATH:
            raise ValueError("ORACLE_KEYPAIR_PATH is required in .env")

        keypath = Path(cls.ORACLE_KEYPAIR_PATH)
        if not keypath.exists():
            raise FileNotFoundError(f"Oracle keypair not found at {keypath}")

        return True


config = Config()