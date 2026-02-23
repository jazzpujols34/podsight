"""Telegram Bot publisher."""

from datetime import datetime
from pathlib import Path
from typing import Any, Optional

import httpx

from .base import BasePublisher, PublishResult


class TelegramPublisher(BasePublisher):
    """Publish to Telegram via Bot API."""

    platform = "telegram"
    API_BASE = "https://api.telegram.org/bot"

    def __init__(self):
        self.token: Optional[str] = None
        self.chat_id: Optional[str] = None
        super().__init__()

    def _load_credentials(self):
        """Load Telegram bot token and chat ID."""
        self.token = self._get_env("TELEGRAM_BOT_TOKEN", required=False)
        self.chat_id = self._get_env("TELEGRAM_CHAT_ID", required=False)

    def is_configured(self) -> bool:
        """Check if Telegram is configured."""
        return bool(self.token and self.chat_id)

    def _api_url(self, method: str) -> str:
        """Build API URL for a method."""
        return f"{self.API_BASE}{self.token}/{method}"

    def publish(self, content: dict[str, Any], image_path: Optional[Path] = None) -> PublishResult:
        """Send message via Telegram Bot API.

        Args:
            content: Dict with 'message' key
            image_path: Optional image to attach

        Returns:
            PublishResult
        """
        if not self.token:
            return PublishResult(
                success=False,
                platform=self.platform,
                post_ids=[],
                error="Telegram not configured. Set TELEGRAM_BOT_TOKEN."
            )

        if not self.chat_id:
            return PublishResult(
                success=False,
                platform=self.platform,
                post_ids=[],
                error="Telegram chat_id not configured. Set TELEGRAM_CHAT_ID."
            )

        message = content.get("message", "")
        if not message:
            return PublishResult(
                success=False,
                platform=self.platform,
                post_ids=[],
                error="No message content"
            )

        try:
            with httpx.Client() as client:
                # Send photo with caption if image provided
                if image_path and image_path.exists():
                    with open(image_path, "rb") as img_file:
                        response = client.post(
                            self._api_url("sendPhoto"),
                            data={
                                "chat_id": self.chat_id,
                                "caption": message[:1024],  # Telegram caption limit
                                "parse_mode": "HTML"
                            },
                            files={"photo": img_file},
                            timeout=30.0
                        )
                else:
                    # Send text message
                    response = client.post(
                        self._api_url("sendMessage"),
                        json={
                            "chat_id": self.chat_id,
                            "text": message,
                            "parse_mode": "HTML",
                            "disable_web_page_preview": True
                        },
                        timeout=30.0
                    )

                result = response.json()

                if result.get("ok"):
                    result_data = result.get("result", {})
                    message_id = result_data.get("message_id", "")
                    # Build URL for channel posts
                    chat_info = result_data.get("chat", result_data.get("sender_chat", {}))
                    username = chat_info.get("username")
                    url = f"https://t.me/{username}/{message_id}" if username else None
                    return PublishResult(
                        success=True,
                        platform=self.platform,
                        post_ids=[str(message_id)],
                        published_at=datetime.now(),
                        url=url
                    )
                else:
                    error_desc = result.get("description", "Unknown error")
                    return PublishResult(
                        success=False,
                        platform=self.platform,
                        post_ids=[],
                        error=f"Telegram API error: {error_desc}"
                    )

        except Exception as e:
            return PublishResult(
                success=False,
                platform=self.platform,
                post_ids=[],
                error=str(e)
            )
