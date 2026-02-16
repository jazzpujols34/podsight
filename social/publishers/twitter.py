"""Twitter/X publisher using tweepy."""

from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from .base import BasePublisher, PublishResult


class TwitterPublisher(BasePublisher):
    """Publish threads to Twitter/X."""

    platform = "twitter"

    def __init__(self):
        self.api_key: Optional[str] = None
        self.api_secret: Optional[str] = None
        self.access_token: Optional[str] = None
        self.access_secret: Optional[str] = None
        self._client = None
        super().__init__()

    def _load_credentials(self):
        """Load Twitter API credentials."""
        self.api_key = self._get_env("TWITTER_API_KEY", required=False)
        self.api_secret = self._get_env("TWITTER_API_SECRET", required=False)
        self.access_token = self._get_env("TWITTER_ACCESS_TOKEN", required=False)
        self.access_secret = self._get_env("TWITTER_ACCESS_SECRET", required=False)

    def is_configured(self) -> bool:
        """Check if Twitter is configured."""
        return all([self.api_key, self.api_secret, self.access_token, self.access_secret])

    def _get_client(self):
        """Get or create tweepy client."""
        if self._client is not None:
            return self._client

        try:
            import tweepy
        except ImportError:
            raise ImportError("tweepy is required for Twitter. Install with: pip install tweepy")

        self._client = tweepy.Client(
            consumer_key=self.api_key,
            consumer_secret=self.api_secret,
            access_token=self.access_token,
            access_token_secret=self.access_secret
        )
        return self._client

    def publish(self, content: dict[str, Any], image_path: Optional[Path] = None) -> PublishResult:
        """Post a thread to Twitter.

        Args:
            content: Dict with 'thread' key containing list of tweet dicts
            image_path: Not used for Twitter threads

        Returns:
            PublishResult with tweet IDs
        """
        if not self.is_configured():
            return PublishResult(
                success=False,
                platform=self.platform,
                post_ids=[],
                error="Twitter not configured. Set TWITTER_API_KEY, TWITTER_API_SECRET, TWITTER_ACCESS_TOKEN, TWITTER_ACCESS_SECRET."
            )

        thread = content.get("thread", [])
        if not thread:
            return PublishResult(
                success=False,
                platform=self.platform,
                post_ids=[],
                error="No thread content"
            )

        try:
            client = self._get_client()
            post_ids = []
            reply_to = None

            for tweet_data in thread:
                text = tweet_data.get("text", "")
                if not text:
                    continue

                # Post tweet (as reply if not first)
                if reply_to:
                    response = client.create_tweet(
                        text=text,
                        in_reply_to_tweet_id=reply_to
                    )
                else:
                    response = client.create_tweet(text=text)

                tweet_id = str(response.data["id"])
                post_ids.append(tweet_id)
                reply_to = tweet_id

            if post_ids:
                return PublishResult(
                    success=True,
                    platform=self.platform,
                    post_ids=post_ids,
                    published_at=datetime.now(),
                    url=f"https://twitter.com/i/status/{post_ids[0]}"
                )
            else:
                return PublishResult(
                    success=False,
                    platform=self.platform,
                    post_ids=[],
                    error="No tweets were posted"
                )

        except Exception as e:
            return PublishResult(
                success=False,
                platform=self.platform,
                post_ids=[],
                error=str(e)
            )
