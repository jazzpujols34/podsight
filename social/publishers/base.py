"""Base publisher class for social media platforms."""

import os
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Optional


@dataclass
class PublishResult:
    """Result of a publish operation."""
    success: bool
    platform: str
    post_ids: list[str]
    published_at: Optional[datetime] = None
    error: Optional[str] = None
    url: Optional[str] = None


class BasePublisher(ABC):
    """Base class for platform publishers."""

    platform: str = "base"

    def __init__(self):
        """Initialize publisher with credentials from environment."""
        self._load_credentials()

    @abstractmethod
    def _load_credentials(self):
        """Load API credentials from environment variables."""
        pass

    @abstractmethod
    def publish(self, content: dict[str, Any], image_path: Optional[Path] = None) -> PublishResult:
        """Publish content to the platform.

        Args:
            content: Platform-specific content dict from formatter
            image_path: Optional path to image (for Instagram)

        Returns:
            PublishResult with success/failure info
        """
        pass

    @abstractmethod
    def is_configured(self) -> bool:
        """Check if the publisher has valid credentials configured."""
        pass

    def _get_env(self, key: str, required: bool = True) -> Optional[str]:
        """Get environment variable with optional requirement."""
        value = os.environ.get(key)
        if required and not value:
            raise ValueError(f"Missing required environment variable: {key}")
        return value
