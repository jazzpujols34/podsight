"""LINE Notify formatter - bullet message format."""

from typing import Any
from .base import BaseFormatter, SummaryContent


class LineFormatter(BaseFormatter):
    """Format content for LINE Notify."""

    platform = "line"
    CHAR_LIMIT = 1000

    def format(self, content: SummaryContent) -> dict[str, Any]:
        """Create LINE Notify message from summary content."""
        message = self._create_message(content)

        return {
            "message": message,
            "char_count": len(message),
        }

    def _create_message(self, content: SummaryContent) -> str:
        """Create LINE message."""
        lines = []

        # Header with emoji
        lines.append(f"🎙️ {content.podcast_name}")
        lines.append(f"📻 {content.episode_id}")
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
                # Strip markdown and shorten long topics
                clean_topic = self.strip_markdown(topic)
                short = clean_topic.split("。")[0]
                if len(short) > 50:
                    short = short[:47] + "..."
                lines.append(f"• {short}")
            lines.append("")

        # Tickers
        tickers = content.get_all_tickers()
        if tickers:
            lines.append(f"📈 提到標的：{', '.join(tickers[:8])}")
            lines.append("")

        # Quote
        if content.quotes:
            quote = self.strip_markdown(content.quotes[0]).strip('"「」')
            if len(quote) > 60:
                quote = quote[:57] + "..."
            lines.append(f"💬 {content.host}：「{quote}」")

        message = "\n".join(lines)

        # LINE has 1000 char limit
        if len(message) > self.CHAR_LIMIT:
            message = message[:self.CHAR_LIMIT - 3] + "..."

        return message
