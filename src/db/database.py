"""Database operations for Oracle Agent."""

import sqlite3
from datetime import datetime
from typing import Optional
from contextlib import contextmanager


class Database:
    """SQLite database for oracle data."""

    def __init__(self, db_path: str = "oracle.db"):
        self.db_path = db_path
        self.init_db()

    def init_db(self):
        """Initialize database tables."""
        with self.get_connection() as conn:
            cursor = conn.cursor()

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS validations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    entry_pda TEXT NOT NULL,
                    pool_pda TEXT NOT NULL,
                    video_a_id TEXT NOT NULL,
                    video_b_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    transcript_score REAL,
                    frame_score REAL,
                    reason TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS metrics_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    entry_pda TEXT NOT NULL,
                    views INTEGER,
                    likes INTEGER,
                    comments INTEGER,
                    score INTEGER,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS fraud_flags (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    entry_pda TEXT NOT NULL,
                    user_wallet TEXT NOT NULL,
                    reason TEXT NOT NULL,
                    slashed BOOLEAN DEFAULT FALSE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS registered_channels (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    channel_id TEXT UNIQUE NOT NULL,
                    owner_authority TEXT,
                    channel_name TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS wrong_channel_alerts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    entry_pda TEXT NOT NULL,
                    creator_wallet TEXT NOT NULL,
                    editor_wallet TEXT,
                    clip_channel_id TEXT NOT NULL,
                    reason TEXT NOT NULL,
                    acknowledged BOOLEAN DEFAULT FALSE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            conn.commit()

    @contextmanager
    def get_connection(self):
        """Get database connection."""
        conn = sqlite3.connect(self.db_path)
        try:
            yield conn
        finally:
            conn.close()

    def save_validation(self, data: dict):
        """Save validation result."""
        with self.get_connection() as conn:
            conn.execute("""
                INSERT INTO validations
                (entry_pda, pool_pda, video_a_id, video_b_id, status, transcript_score, frame_score, reason)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                data["entry_pda"],
                data["pool_pda"],
                data["video_a_id"],
                data["video_b_id"],
                data["status"],
                data.get("transcript_score"),
                data.get("frame_score"),
                data.get("reason"),
            ))
            conn.commit()

    def save_metrics(self, entry_pda: str, views: int, likes: int, comments: int, score: int):
        """Save metrics update."""
        with self.get_connection() as conn:
            conn.execute("""
                INSERT INTO metrics_history (entry_pda, views, likes, comments, score)
                VALUES (?, ?, ?, ?, ?)
            """, (entry_pda, views, likes, comments, score))
            conn.commit()

    def flag_fraud(self, entry_pda: str, user_wallet: str, reason: str):
        """Flag an entry for fraud."""
        with self.get_connection() as conn:
            conn.execute("""
                INSERT INTO fraud_flags (entry_pda, user_wallet, reason)
                VALUES (?, ?, ?)
            """, (entry_pda, user_wallet, reason))
            conn.commit()

    def get_validation_reason(self, entry_pda: str) -> Optional[str]:
        """Get rejection reason for an entry."""
        with self.get_connection() as conn:
            cursor = conn.execute(
                "SELECT reason FROM validations WHERE entry_pda = ? ORDER BY id DESC LIMIT 1",
                (entry_pda,)
            )
            row = cursor.fetchone()
            return row[0] if row else None

    def save_registered_channel(self, channel_id: str, owner_authority: str, channel_name: str = None):
        """Salva canal registrado no sistema (quando initializeUser é usado)."""
        with self.get_connection() as conn:
            conn.execute("""
                INSERT OR REPLACE INTO registered_channels (channel_id, owner_authority, channel_name)
                VALUES (?, ?, ?)
            """, (channel_id, owner_authority, channel_name))
            conn.commit()

    def is_channel_registered(self, channel_id: str) -> bool:
        """Verifica se canal já está registrado no sistema."""
        with self.get_connection() as conn:
            cursor = conn.execute(
                "SELECT 1 FROM registered_channels WHERE channel_id = ?",
                (channel_id,)
            )
            return cursor.fetchone() is not None

    def get_channel_owner(self, channel_id: str) -> Optional[str]:
        """Retorna o owner (wallet) de um canal registrado."""
        with self.get_connection() as conn:
            cursor = conn.execute(
                "SELECT owner_authority FROM registered_channels WHERE channel_id = ?",
                (channel_id,)
            )
            row = cursor.fetchone()
            return row[0] if row else None

    def get_all_registered_channels(self) -> list[dict]:
        """Retorna todos os canais registrados."""
        with self.get_connection() as conn:
            cursor = conn.execute("SELECT channel_id, owner_authority, channel_name FROM registered_channels")
            return [{"channel_id": r[0], "owner_authority": r[1], "channel_name": r[2]} for r in cursor.fetchall()]

    def save_wrong_channel_alert(
        self,
        entry_pda: str,
        creator_wallet: str,
        editor_wallet: str,
        clip_channel_id: str,
        reason: str,
    ):
        """Salva alerta de wrong channel para o frontend."""
        with self.get_connection() as conn:
            conn.execute("""
                INSERT INTO wrong_channel_alerts
                (entry_pda, creator_wallet, editor_wallet, clip_channel_id, reason)
                VALUES (?, ?, ?, ?, ?)
            """, (entry_pda, creator_wallet, editor_wallet, clip_channel_id, reason))
            conn.commit()

    def get_pending_wrong_channel_alerts(self) -> list[dict]:
        """Retorna alertas de wrong channel pendentes."""
        with self.get_connection() as conn:
            cursor = conn.execute("""
                SELECT id, entry_pda, creator_wallet, editor_wallet, clip_channel_id, reason, created_at
                FROM wrong_channel_alerts WHERE acknowledged = FALSE ORDER BY created_at DESC
            """)
            return [
                {"id": r[0], "entry_pda": r[1], "creator_wallet": r[2], "editor_wallet": r[3],
                 "clip_channel_id": r[4], "reason": r[5], "created_at": r[6]}
                for r in cursor.fetchall()
            ]

    def acknowledge_wrong_channel_alert(self, alert_id: int):
        """Marca alerta de wrong channel como reconhecido."""
        with self.get_connection() as conn:
            conn.execute(
                "UPDATE wrong_channel_alerts SET acknowledged = TRUE WHERE id = ?",
                (alert_id,)
            )
            conn.commit()