"""Alert service for Oracle Agent notifications."""

import os
from typing import Optional
import httpx
from loguru import logger


class AlertService:
    """Serviço de notificação para alertas do Oracle."""

    def __init__(self):
        self.webhook_url = os.getenv("ALERT_WEBHOOK_URL", "")
        self.enabled = bool(self.webhook_url)

    async def notify_wrong_channel(
        self,
        entry_pda: str,
        creator_wallet: str,
        editor_wallet: str,
        clip_channel_id: str,
        reason: str,
    ):
        """
        Notifica sobre WRONG_CHANNEL (vídeo do creator mas canal diferente).
        
        Este caso NÃO deve executar slash — apenas alerta o frontend.
        
        Args:
            entry_pda: Endereço da entry na blockchain
            creator_wallet: Carteira do criador da pool
            editor_wallet: Carteira do editor que submeteu
            clip_channel_id: ID do canal onde o vídeo foi postado
            reason: Motivo do alerta
        """
        logger.warning(
            f"WRONG_CHANNEL Alert: entry={entry_pda}, "
            f"creator={creator_wallet}, clip_channel={clip_channel_id}, reason={reason}"
        )

        try:
            from ..db.database import Database
            db = Database()
            db.save_wrong_channel_alert(
                entry_pda=entry_pda,
                creator_wallet=creator_wallet,
                editor_wallet=editor_wallet,
                clip_channel_id=clip_channel_id,
                reason=reason,
            )
        except Exception as e:
            logger.error(f"Failed to save wrong_channel alert to DB: {e}")

        if self.enabled:
            await self._send_webhook({
                "type": "WRONG_CHANNEL",
                "entry_pda": entry_pda,
                "creator_wallet": creator_wallet,
                "editor_wallet": editor_wallet,
                "clip_channel_id": clip_channel_id,
                "reason": reason,
            })

    async def notify_fraud(
        self,
        entry_pda: str,
        user_wallet: str,
        reason: str,
    ):
        """
        Notifica sobre FRAUD detectada e executa slash.
        
        Este caso DEVE executar slash_user via CPI.
        
        Args:
            entry_pda: Endereço da entry
            user_wallet: Carteira do usuário fraudulento
            reason: Motivo da detecção
        """
        logger.error(
            f"FRAUD DETECTED: entry={entry_pda}, "
            f"user={user_wallet}, reason={reason}"
        )

        try:
            from ..db.database import Database
            db = Database()
            db.flag_fraud(entry_pda, user_wallet, reason)
        except Exception as e:
            logger.error(f"Failed to flag fraud: {e}")

        if self.enabled:
            await self._send_webhook({
                "type": "FRAUD",
                "entry_pda": entry_pda,
                "user_wallet": user_wallet,
                "reason": reason,
                "action": "SLASH_USER",
            })

    async def _send_webhook(self, payload: dict):
        """Envia payload para o webhook configurado."""
        if not self.enabled:
            return

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(
                    self.webhook_url,
                    json=payload,
                    headers={"Content-Type": "application/json"},
                )
                response.raise_for_status()
                logger.info(f"Webhook sent successfully: {payload['type']}")
        except Exception as e:
            logger.error(f"Failed to send webhook: {e}")


alert_service = AlertService()