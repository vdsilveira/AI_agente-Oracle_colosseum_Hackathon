"""Configuration module for Oracle Agent."""

import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()


class Config:
    """Oracle Agent configuration."""

    APP_API_KEY: str = os.getenv("APP_API_KEY", "")
    SOLANA_RPC_URL: str = os.getenv("SOLANA_RPC_URL", "https://api.devnet.solana.com")
    ORACLE_PUBLIC_KEY: str = os.getenv("ORACLE_PUBLIC_KEY", "")
    ORACLE_PRIVATE_KEY: str = os.getenv("ORACLE_PRIVATE_KEY", "")

    METRICS_API_URL: str = os.getenv("METRICS_API_URL", "https://backend-views-solana.onrender.com")
    METRICS_API_KEY: str = os.getenv("METRICS_API_KEY", "")

    TRANSCRIPT_MIN_SCORE: float = float(os.getenv("TRANSCRIPT_MIN_SCORE", "0.70"))
    FRAME_SIMILARITY_THRESHOLD: float = float(os.getenv("FRAME_SIMILARITY_THRESHOLD", "0.70"))
    FRAME_MIN_MATCHES: int = int(os.getenv("FRAME_MIN_MATCHES", "3"))
    FRAME_TOTAL_SAMPLES: int = int(os.getenv("FRAME_TOTAL_SAMPLES", "5"))

    POLL_INTERVAL_SECONDS: int = int(os.getenv("POLL_INTERVAL_SECONDS", "60"))

    HTTP_PROXY: str = os.getenv("HTTP_PROXY", "")
    HTTPS_PROXY: str = os.getenv("HTTPS_PROXY", "")

    DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite:///oracle.db")

    PROGRAM_ID: str = os.getenv("PROGRAM_ID", "4RAbxbEVCsYaaK3WR8r7eYwrofTJ7yqdZ3hqSYRLPfT4")

    CORE_API_URL: str = os.getenv("CORE_API_URL", "http://localhost:8001/api/v1")

    ALERT_WEBHOOK_URL: str = os.getenv("ALERT_WEBHOOK_URL", "")
    YOUTUBE_COOKIES_PATH: str = os.getenv("YOUTUBE_COOKIES_PATH", "")

    WHISPER_MODEL_SIZE: str = os.getenv("WHISPER_MODEL_SIZE", "tiny")
    WHISPER_DEVICE: str = os.getenv("WHISPER_DEVICE", "cpu")

    @classmethod
    def validate(cls) -> bool:
        """Validate required configuration."""
        if not cls.APP_API_KEY:
            raise ValueError("APP_API_KEY is required in .env")
        if not cls.SOLANA_RPC_URL:
            raise ValueError("SOLANA_RPC_URL is required in .env")
        if not cls.ORACLE_PUBLIC_KEY:
            raise ValueError("ORACLE_PUBLIC_KEY is required in .env")
        if not cls.ORACLE_PRIVATE_KEY:
            raise ValueError("ORACLE_PRIVATE_KEY is required in .env")

        return True


config = Config()