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