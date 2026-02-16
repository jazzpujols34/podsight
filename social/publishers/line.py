"""LINE Notify publisher."""

from datetime import datetime
from pathlib import Path
from typing import Any, Optional

import httpx

from .base import BasePublisher, PublishResult


class LinePublisher(BasePublisher):
    """Publish to LINE Notify."""

    platform = "line"
    API_URL = "https://notify-api.line.me/api/notify"

    def __init__(self):
        self.token: Optional[str] = None
        super().__init__()

    def _load_credentials(self):
        """Load LINE Notify token."""
        self.token = self._get_env("LINE_NOTIFY_TOKEN", required=False)

    def is_configured(self) -> bool:
        """Check if LINE Notify is configured."""
        return bool(self.token)

    def publish(self, content: dict[str, Any], image_path: Optional[Path] = None) -> PublishResult:
        """Send message via LINE Notify.

        Args:
            content: Dict with 'message' key
            image_path: Optional image to attach

        Returns:
            PublishResult
        """
        if not self.is_configured():
            return PublishResult(
                success=False,
                platform=self.platform,
                post_ids=[],
                error="LINE Notify not configured. Set LINE_NOTIFY_TOKEN."
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
            headers = {"Authorization": f"Bearer {self.token}"}
            data = {"message": message}

            # Attach image if provided
            files = None
            if image_path and image_path.exists():
                files = {"imageFile": open(image_path, "rb")}

            with httpx.Client() as client:
                response = client.post(
                    self.API_URL,
                    headers=headers,
                    data=data,
                    files=files,
                    timeout=30.0
                )

            if response.status_code == 200:
                return PublishResult(
                    success=True,
                    platform=self.platform,
                    post_ids=["line_notify"],
                    published_at=datetime.now()
                )
            else:
                return PublishResult(
                    success=False,
                    platform=self.platform,
                    post_ids=[],
                    error=f"LINE API error: {response.status_code} - {response.text}"
                )

        except Exception as e:
            return PublishResult(
                success=False,
                platform=self.platform,
                post_ids=[],
                error=str(e)
            )
