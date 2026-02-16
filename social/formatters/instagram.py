"""Instagram formatter - image card + caption."""

from typing import Any
from .base import BaseFormatter, SummaryContent


class InstagramFormatter(BaseFormatter):
    """Format content for Instagram (image card + caption)."""

    platform = "instagram"
    CAPTION_LIMIT = 2200

    def format(self, content: SummaryContent) -> dict[str, Any]:
        """Create Instagram post config from summary content."""
        caption = self._create_caption(content)
        image_config = self._create_image_config(content)
        hashtags = self._generate_hashtags(content)

        return {
            "caption": caption,
            "char_count": len(caption),
            "image_config": image_config,
            "hashtags": hashtags,
        }

    def _create_caption(self, content: SummaryContent) -> str:
        """Create Instagram caption."""
        lines = []

        # Title
        lines.append(f"🎙️ {content.episode_id} {content.podcast_name}")
        lines.append("")

        # One-liner
        if content.one_liner:
            one_liner = self.strip_markdown(content.one_liner).strip('"「」')
            lines.append(f"📝 {one_liner}")
            lines.append("")

        # Topics
        if content.topics:
            lines.append("💡 本集重點：")
            for topic in content.topics[:4]:
                clean_topic = self.strip_markdown(topic)
                short = clean_topic.split("。")[0]
                lines.append(f"• {short}")
            lines.append("")

        # Quote
        if content.quotes:
            quote = self.strip_markdown(content.quotes[0]).strip('"「」')
            lines.append(f"💬「{quote}」")
            lines.append(f"— {content.host}")
            lines.append("")

        # CTA
        lines.append("🎧 完整內容請收聽 Podcast")
        lines.append("")

        # Hashtags
        hashtags = self._generate_hashtags(content)
        lines.append(" ".join(hashtags))

        caption = "\n".join(lines)
        return caption[:self.CAPTION_LIMIT]

    def _create_image_config(self, content: SummaryContent) -> dict:
        """Create config for image generation."""
        # Prepare body text (key points)
        body_points = []
        for topic in content.topics[:3]:
            clean_topic = self.strip_markdown(topic)
            short = clean_topic.split("。")[0].split("，")[0]
            if len(short) > 30:
                short = short[:27] + "..."
            body_points.append(short)

        one_liner = self.strip_markdown(content.one_liner).strip('"「」')[:60] if content.one_liner else ""
        quote = self.strip_markdown(content.quotes[0]).strip('"「」')[:50] if content.quotes else ""

        return {
            "background": "#1a1a2e",  # Dark theme
            "accent_color": "#f59e0b",  # PodSight amber
            "title": f"{content.episode_id}",
            "subtitle": content.podcast_name,
            "one_liner": one_liner,
            "body_points": body_points,
            "tickers": content.get_all_tickers()[:6],
            "quote": quote,
            "host": content.host,
        }

    def _generate_hashtags(self, content: SummaryContent) -> list[str]:
        """Generate Instagram hashtags."""
        tags = []

        # Podcast-specific
        if "股癌" in content.podcast_name:
            tags.extend(["#股癌", "#gooaye"])
        elif "游庭皓" in content.podcast_name:
            tags.extend(["#游庭皓", "#財經皓角"])
        elif "兆華" in content.podcast_name:
            tags.extend(["#兆華與股惑仔", "#兆華"])

        # Generic finance tags
        tags.extend([
            "#投資", "#理財", "#股票",
            "#podcast", "#投資筆記", "#財經",
            "#台股", "#美股", "#ETF"
        ])

        return tags[:15]  # IG allows up to 30, but 10-15 is optimal
