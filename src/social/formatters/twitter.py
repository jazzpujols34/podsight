"""Twitter/X formatter - creates thread format (Hook + Replies)."""

from typing import Any
from .base import BaseFormatter, SummaryContent


class TwitterFormatter(BaseFormatter):
    """Format content as Twitter/X thread with Hook + Replies structure.

    Main tweet: Hook with title + one-liner + key highlights
    Replies: Details, tickers, quotes
    """

    platform = "twitter"
    CHAR_LIMIT = 280
    VERIFIED_LIMIT = 4000  # Verified accounts can post longer

    def format(self, content: SummaryContent) -> dict[str, Any]:
        """Create a Twitter thread from summary content."""
        thread = []
        hashtags = self._generate_hashtags(content)
        cashtags = self._generate_cashtags(content)

        # Main Tweet: Hook with title + one-liner + key highlights
        main_tweet = self._create_main_tweet(content)
        thread.append({
            "text": main_tweet,
            "char_count": self.count_chars(main_tweet),
            "is_main": True
        })

        # Reply 1: Key topics
        topics_reply = self._create_topics_reply(content)
        if topics_reply:
            thread.append({
                "text": topics_reply,
                "char_count": self.count_chars(topics_reply),
                "is_main": False
            })

        # Reply 2: Tickers
        tickers = content.get_all_tickers()
        if tickers:
            ticker_reply = self._create_ticker_reply(content, cashtags)
            thread.append({
                "text": ticker_reply,
                "char_count": self.count_chars(ticker_reply),
                "is_main": False
            })

        # Reply 3: Quote + hashtags
        if content.quotes:
            quote_reply = self._create_quote_reply(content, hashtags)
            thread.append({
                "text": quote_reply,
                "char_count": self.count_chars(quote_reply),
                "is_main": False
            })

        return {
            "thread": thread,
            "total_tweets": len(thread),
            "hashtags": hashtags,
            "cashtags": cashtags,
        }

    def _create_main_tweet(self, content: SummaryContent) -> str:
        """Create main tweet with hook: title + one-liner + highlights."""
        lines = []

        # Title line: "Gooaye 股癌 EP636 重點整理"
        if "股癌" in content.podcast_name:
            lines.append(f"🎙️ Gooaye 股癌 {content.episode_id} 重點整理")
        elif "游庭皓" in content.podcast_name:
            lines.append(f"🎙️ 財經皓角 {content.episode_id} 重點整理")
        elif "兆華" in content.podcast_name:
            lines.append(f"🎙️ 兆華與股惑仔 {content.episode_id} 重點整理")
        else:
            lines.append(f"🎙️ {content.podcast_name} {content.episode_id} 重點整理")

        lines.append("")

        # One-liner
        if content.one_liner:
            one_liner = self.strip_markdown(content.one_liner).strip('"「」')
            lines.append(f"📝 {one_liner}")
            lines.append("")

        # 2-3 key highlights (short version)
        if content.topics:
            lines.append("💡 本集亮點：")
            for topic in content.topics[:3]:
                clean_topic = self.strip_markdown(topic)
                # Extract just the title part (before colon)
                short = clean_topic.split("：")[0].split(":")[0]
                if len(short) > 25:
                    short = short[:22] + "..."
                lines.append(f"• {short}")

        lines.append("")
        lines.append("👇 詳細內容請看回覆")

        return "\n".join(lines)

    def _create_topics_reply(self, content: SummaryContent) -> str:
        """Create reply with detailed discussion topics."""
        if not content.topics:
            return ""

        lines = ["💡 本集重點：", ""]

        for topic in content.topics[:5]:  # Limit to 5 topics
            clean_topic = self.strip_markdown(topic)
            # Truncate long topics
            if len(clean_topic) > 80:
                clean_topic = clean_topic[:77] + "..."
            lines.append(f"• {clean_topic}")

        return "\n".join(lines)

    def _create_ticker_reply(self, content: SummaryContent, cashtags: list[str]) -> str:
        """Create reply with stock tickers."""
        lines = ["📈 本集提到的標的：", ""]

        # US stocks as cashtags
        us_tickers = content.get_us_tickers()
        if us_tickers:
            cashtag_str = " ".join(f"${t}" for t in us_tickers[:6])
            lines.append(f"美股：{cashtag_str}")

        # Taiwan stocks
        tw_tickers = content.tickers.get("台股", [])
        if tw_tickers:
            lines.append(f"台股：{', '.join(tw_tickers[:5])}")

        # ETFs
        etfs = content.tickers.get("ETF", [])
        if etfs:
            lines.append(f"ETF：{', '.join(etfs[:3])}")

        return "\n".join(lines)

    def _create_quote_reply(self, content: SummaryContent, hashtags: list[str]) -> str:
        """Create reply with host quote and hashtags."""
        lines = []

        # Quote
        quote = content.quotes[0] if content.quotes else ""
        quote = self.strip_markdown(quote).strip('"「」')

        lines.append(f"💬 {content.host}金句：")
        lines.append(f"「{quote}」")
        lines.append("")

        # Hashtags
        if hashtags:
            lines.append(" ".join(hashtags))

        return "\n".join(lines)

    def _generate_hashtags(self, content: SummaryContent) -> list[str]:
        """Generate relevant hashtags."""
        tags = []

        # Podcast-specific
        if "股癌" in content.podcast_name:
            tags.append("#股癌")
        elif "游庭皓" in content.podcast_name:
            tags.append("#游庭皓")
        elif "兆華" in content.podcast_name:
            tags.append("#兆華")

        # Generic
        tags.extend(["#投資", "#理財"])

        return tags[:4]  # Limit hashtags

    def _generate_cashtags(self, content: SummaryContent) -> list[str]:
        """Generate cashtags from US tickers."""
        us_tickers = content.get_us_tickers()
        return [f"${t}" for t in us_tickers[:5]]
