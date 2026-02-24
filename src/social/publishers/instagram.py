"""Instagram publisher using Meta Graph API."""

import time
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

import httpx

from .base import BasePublisher, PublishResult


class InstagramPublisher(BasePublisher):
    """Publish to Instagram (Business/Creator account)."""

    platform = "instagram"
    API_BASE = "https://graph.facebook.com/v18.0"

    def __init__(self):
        self.access_token: Optional[str] = None
        self.user_id: Optional[str] = None
        super().__init__()

    def _load_credentials(self):
        """Load Meta/Instagram API credentials."""
        self.access_token = self._get_env("META_ACCESS_TOKEN", required=False)
        self.user_id = self._get_env("META_INSTAGRAM_USER_ID", required=False)

    def is_configured(self) -> bool:
        """Check if Instagram is configured."""
        return bool(self.access_token and self.user_id)

    def publish(self, content: dict[str, Any], image_path: Optional[Path] = None) -> PublishResult:
        """Post image to Instagram.

        Args:
            content: Dict with 'caption' key
            image_path: Path to image file (required for IG)

        Returns:
            PublishResult
        """
        if not self.is_configured():
            return PublishResult(
                success=False,
                platform=self.platform,
                post_ids=[],
                error="Instagram not configured. Set META_ACCESS_TOKEN and META_INSTAGRAM_USER_ID."
            )

        caption = content.get("caption", "")
        if not image_path or not image_path.exists():
            return PublishResult(
                success=False,
                platform=self.platform,
                post_ids=[],
                error="Image file required for Instagram"
            )

        try:
            with httpx.Client() as client:
                # Step 1: Upload image to get a container
                # Note: Instagram API requires image URL, not direct upload
                # For local images, you need to host them first
                # This is a simplified implementation assuming hosted images

                # For now, return error indicating manual upload needed
                return PublishResult(
                    success=False,
                    platform=self.platform,
                    post_ids=[],
                    error="Instagram requires hosted image URL. Manual upload recommended. Image saved at: " + str(image_path)
                )

                # Full implementation would be:
                # 1. Upload image to a hosting service (S3, Cloudinary, etc.)
                # 2. Get public URL
                # 3. Create media container with image_url
                # 4. Publish container

        except Exception as e:
            return PublishResult(
                success=False,
                platform=self.platform,
                post_ids=[],
                error=str(e)
            )

    def publish_with_url(self, caption: str, image_url: str) -> PublishResult:
        """Post to Instagram using a hosted image URL.

        Args:
            caption: Post caption
            image_url: Public URL of the image

        Returns:
            PublishResult
        """
        if not self.is_configured():
            return PublishResult(
                success=False,
                platform=self.platform,
                post_ids=[],
                error="Instagram not configured"
            )

        try:
            with httpx.Client() as client:
                # Step 1: Create media container
                create_url = f"{self.API_BASE}/{self.user_id}/media"
                create_response = client.post(
                    create_url,
                    params={
                        "image_url": image_url,
                        "caption": caption,
                        "access_token": self.access_token
                    },
                    timeout=60.0
                )

                if create_response.status_code != 200:
                    return PublishResult(
                        success=False,
                        platform=self.platform,
                        post_ids=[],
                        error=f"Failed to create container: {create_response.text}"
                    )

                container_id = create_response.json().get("id")

                # Wait for processing
                time.sleep(5)

                # Step 2: Publish the container
                publish_url = f"{self.API_BASE}/{self.user_id}/media_publish"
                publish_response = client.post(
                    publish_url,
                    params={
                        "creation_id": container_id,
                        "access_token": self.access_token
                    },
                    timeout=60.0
                )

                if publish_response.status_code == 200:
                    post_id = publish_response.json().get("id", container_id)
                    return PublishResult(
                        success=True,
                        platform=self.platform,
                        post_ids=[post_id],
                        published_at=datetime.now(),
                        url=f"https://www.instagram.com/p/{post_id}"
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
