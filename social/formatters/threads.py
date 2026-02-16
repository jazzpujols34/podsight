"""Threads formatter - single post format."""

from typing import Any
from .base import BaseFormatter, SummaryContent


class ThreadsFormatter(BaseFormatter):
    """Format content for Threads (Meta)."""

    platform = "threads"
    CHAR_LIMIT = 500

    def format(self, content: SummaryContent) -> dict[str, Any]:
        """Create a Threads post from summary content."""
        post = self._create_post(content)
        hashtags = self._generate_hashtags(content)

        return {
            "text": post,
            "char_count": self.count_chars(post),
            "hashtags": hashtags,
        }

    def _create_post(self, content: SummaryContent) -> str:
        """Create single Threads post."""
        lines = []

        # Header
        lines.append(f"📻 {content.episode_id} {content.podcast_name}")
        lines.append("")

        # One-liner
        if content.one_liner:
            one_liner = self.strip_markdown(content.one_liner).strip('"「」')
            lines.append(f"📝 {one_liner}")
            lines.append("")

        # Key topics (condensed)
        if content.topics:
            lines.append("💡 重點：")
            for topic in content.topics[:3]:
                # Strip markdown and take first sentence of each topic
                clean_topic = self.strip_markdown(topic)
                short_topic = clean_topic.split("。")[0].split("，")[0]
                lines.append(f"• {short_topic}")
            lines.append("")

        # Tickers
        all_tickers = content.get_all_tickers()
        if all_tickers:
            lines.append(f"📈 標的：{', '.join(all_tickers[:6])}")
            lines.append("")

        # Quote
        if content.quotes:
            quote = self.strip_markdown(content.quotes[0]).strip('"「」')
            short_quote = self.truncate_to_limit(quote, 80)
            lines.append(f"💬「{short_quote}」")
            lines.append("")

        # Hashtags
        hashtags = self._generate_hashtags(content)
        if hashtags:
            lines.append(" ".join(hashtags))

        post = "\n".join(lines)
        return self.truncate_to_limit(post, self.CHAR_LIMIT)

    def _generate_hashtags(self, content: SummaryContent) -> list[str]:
        """Generate hashtags for Threads."""
        tags = []

        if "股癌" in content.podcast_name:
            tags.append("#股癌")
        elif "游庭皓" in content.podcast_name:
            tags.append("#游庭皓")
        elif "兆華" in content.podcast_name:
            tags.append("#兆華與股惑仔")

        tags.extend(["#投資筆記", "#Podcast"])
        return tags[:4]
