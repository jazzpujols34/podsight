"""Telegram formatter - comprehensive format with full content."""

import re
from typing import Any
from .base import BaseFormatter, SummaryContent


class TelegramFormatter(BaseFormatter):
    """Format content for Telegram Bot API."""

    platform = "telegram"
    CHAR_LIMIT = 4096  # Telegram message limit

    def format(self, content: SummaryContent) -> dict[str, Any]:
        """Create Telegram message from summary content."""
        message = self._create_message(content)

        return {
            "message": message,
            "char_count": len(message),
        }

    def _create_message(self, content: SummaryContent) -> str:
        """Create Telegram message with HTML formatting - comprehensive version."""
        lines = []

        # Header
        lines.append(f"<b>{content.podcast_name}</b>")
        lines.append(f"{content.episode_id}")
        lines.append("")

        # One-liner
        if content.one_liner:
            one_liner = self.strip_markdown(content.one_liner).strip('"「」')
            lines.append(f"<i>{one_liner}</i>")
            lines.append("")

        # Topics - extract main topics only (not sub-bullets)
        main_topics = self._extract_main_topics(content.raw_text)
        if main_topics:
            lines.append("<b>主要討論話題：</b>")
            for topic in main_topics[:6]:  # Up to 6 main topics
                clean_topic = self.strip_markdown(topic)
                if len(clean_topic) > 150:
                    clean_topic = clean_topic[:147] + "..."
                lines.append(f"• {clean_topic}")
            lines.append("")

        # Tickers
        tickers = content.get_all_tickers()
        if tickers:
            ticker_list = ", ".join(tickers[:10])  # Limit to 10
            lines.append(f"<b>提到的標的：</b> {ticker_list}")
            lines.append("")

        # Quotes
        if content.quotes:
            lines.append(f"<b>{content.host} 金句：</b>")
            for quote in content.quotes[:3]:
                clean_quote = self.strip_markdown(quote).strip('"「」')
                if len(clean_quote) > 150:
                    clean_quote = clean_quote[:147] + "..."
                lines.append(f"「{clean_quote}」")
            lines.append("")

        # 冷笑話 section (for yutinghao)
        jokes = self._extract_jokes(content.raw_text)
        if jokes:
            lines.append("<b>冷笑話精選：</b>")
            for joke in jokes[:2]:  # Up to 2 jokes
                clean_joke = self.strip_markdown(joke)
                if len(clean_joke) > 200:
                    clean_joke = clean_joke[:197] + "..."
                lines.append(f"• {clean_joke}")
            lines.append("")

        message = "\n".join(lines)

        # Enforce limit - truncate if needed
        if len(message) > self.CHAR_LIMIT:
            message = message[:self.CHAR_LIMIT - 50] + "\n\n<i>...內容過長，已截斷</i>"

        return message

    def _extract_main_topics(self, text: str) -> list[str]:
        """Extract only main topic headers, not sub-bullets."""
        topics = []
        in_topics_section = False
        # Skip these sub-header patterns
        skip_patterns = ['詳細說明', '市場影響', '投資啟示', '市場背景', '相關標的', '說明']

        for line in text.split('\n'):
            stripped = line.strip()

            # Start of topics section
            if '主要討論話題' in stripped:
                in_topics_section = True
                continue

            # End of topics section (next ### header or ---)
            if in_topics_section and (stripped.startswith('###') or stripped.startswith('---')):
                break

            # Main topic patterns:
            # 1. Bullet: * **Topic** or - **Topic**
            # 2. Numbered: 1. **Topic** or 1.  **Topic**
            is_main_topic = (
                re.match(r'^[-*]\s+\*\*', stripped) or  # * **Topic**
                re.match(r'^\d+\.\s+\*\*', stripped)     # 1. **Topic**
            )

            if in_topics_section and is_main_topic:
                # Check if this line is NOT indented in the original
                if line.startswith('    ') or line.startswith('\t'):
                    continue  # Skip indented sub-bullets

                # Extract the bold topic name
                match = re.search(r'\*\*(.+?)\*\*', stripped)
                if match:
                    topic_name = match.group(1).rstrip('：:')
                    # Skip sub-header patterns
                    if any(skip in topic_name for skip in skip_patterns):
                        continue
                    topics.append(topic_name)

        return topics

    def _extract_jokes(self, text: str) -> list[str]:
        """Extract jokes from 冷笑話 section."""
        jokes = []

        # Find 冷笑話 section
        match = re.search(r'冷笑話.*?\n(.*?)(?=\n###|\n---|\Z)', text, re.DOTALL | re.IGNORECASE)
        if not match:
            return jokes

        section = match.group(1)

        # Parse jokes - each starts with * ** title **: and content follows
        current_joke = []
        for line in section.split('\n'):
            stripped = line.strip()
            if not stripped:
                continue

            # New joke header
            if re.match(r'^[-*]\s+\*\*', stripped):
                if current_joke:
                    jokes.append(' '.join(current_joke))
                # Extract title and start content
                title_match = re.search(r'\*\*(.+?)[：:]\*\*', stripped)
                if title_match:
                    current_joke = [f"【{title_match.group(1)}】"]
                else:
                    current_joke = []
            elif current_joke and stripped.startswith('「'):
                # Content line
                current_joke.append(stripped.strip('「」'))

        if current_joke:
            jokes.append(' '.join(current_joke))

        return jokes
