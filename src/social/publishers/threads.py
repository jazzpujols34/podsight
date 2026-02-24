"""Threads publisher using Meta Graph API."""

from datetime import datetime
from pathlib import Path
from typing import Any, Optional

import httpx

from .base import BasePublisher, PublishResult


class ThreadsPublisher(BasePublisher):
    """Publish to Threads (Meta)."""

    platform = "threads"
    API_BASE = "https://graph.threads.net/v1.0"

    def __init__(self):
        self.access_token: Optional[str] = None
        self.user_id: Optional[str] = None
        super().__init__()

    def _load_credentials(self):
        """Load Meta/Threads API credentials."""
        self.access_token = self._get_env("META_ACCESS_TOKEN", required=False)
        self.user_id = self._get_env("META_THREADS_USER_ID", required=False)

    def is_configured(self) -> bool:
        """Check if Threads is configured."""
        return bool(self.access_token and self.user_id)

    def publish(self, content: dict[str, Any], image_path: Optional[Path] = None) -> PublishResult:
        """Post to Threads.

        Args:
            content: Dict with 'text' key
            image_path: Not used for text posts

        Returns:
            PublishResult
        """
        if not self.is_configured():
            return PublishResult(
                success=False,
                platform=self.platform,
                post_ids=[],
                error="Threads not configured. Set META_ACCESS_TOKEN and META_THREADS_USER_ID."
            )

        text = content.get("text", "")
        if not text:
            return PublishResult(
                success=False,
                platform=self.platform,
                post_ids=[],
                error="No text content"
            )

        try:
            with httpx.Client() as client:
                # Step 1: Create media container
                create_url = f"{self.API_BASE}/{self.user_id}/threads"
                create_response = client.post(
                    create_url,
                    params={
                        "media_type": "TEXT",
                        "text": text,
                        "access_token": self.access_token
                    },
                    timeout=30.0
                )

                if create_response.status_code != 200:
                    return PublishResult(
                        success=False,
                        platform=self.platform,
                        post_ids=[],
                        error=f"Failed to create container: {create_response.text}"
                    )

                container_id = create_response.json().get("id")

                # Step 2: Publish the container
                publish_url = f"{self.API_BASE}/{self.user_id}/threads_publish"
                publish_response = client.post(
                    publish_url,
                    params={
                        "creation_id": container_id,
                        "access_token": self.access_token
                    },
                    timeout=30.0
                )

                if publish_response.status_code == 200:
                    post_id = publish_response.json().get("id", container_id)
                    return PublishResult(
                        success=True,
                        platform=self.platform,
                        post_ids=[post_id],
                        published_at=datetime.now(),
                        url=f"https://www.threads.net/@{self.user_id}/post/{post_id}"
                    )
                else:
                    return PublishResult(
                        success=False,
                        platform=self.platform,
                        post_ids=[],
                        error=f"Failed to publish: {publish_response.text}"
                    )

        except Exception as e:
            return PublishResult(
                success=False,
                platform=self.platform,
                post_ids=[],
                error=str(e)
            )
