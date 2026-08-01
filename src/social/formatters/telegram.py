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

        # Add frontend link
        if content.podcast_slug:
            url = content.get_frontend_url()
            lines.append(f'🔗 <a href="{url}">閱讀完整摘要</a>')
            lines.append("")

        message = "\n".join(lines)

        # Enforce limit - truncate if needed
        if len(message) > self.CHAR_LIMIT:
            message = message[:self.CHAR_LIMIT - 50] + "\n\n<i>...內容過長，已截斷</i>"

        return message

    # Structural sub-headers — safe to match as substrings because no real topic
    # name contains them.
    _TOPIC_SKIP_SUBSTRINGS = [
        '詳細說明', '市場影響', '投資啟示', '市場背景', '相關標的', '說明',
    ]
    # `話題名稱：` is a LABEL, not a topic — but the two shows use it differently:
    #   yutinghao: `- **話題名稱：台積電權重巨獸與內外資對作**`  (real name follows)
    #   gooaye:    `*   **話題名稱：** ...`                      (name is outside the bold)
    # So strip the prefix rather than skipping the line; an empty remainder is
    # then dropped by the falsy-name check at each call site.
    _TOPIC_LABEL_PREFIX = re.compile(r'^話題名稱\s*[：:]\s*')
    # Generic in-body labels that leaked into gooaye previews (e.g. `**MK 的觀點：** ...`).
    # Matched EXACTLY against the name's pre-colon head, so a legitimate topic like
    # 「殺人心盤的操作邏輯」 is never dropped for merely containing 「操作邏輯」.
    _TOPIC_SKIP_EXACT = {
        'MK 的觀點', 'MK 的推論', 'MK 的觀點與推論', 'MK 認為', '市場認為',
        '操作邏輯', '具體觀察', 'MK 的具體觀察', '個人案例',
    }

    def _is_generic_label(self, name: str) -> bool:
        """True if `name` is a sub-header/label rather than a real topic name."""
        if any(kw in name for kw in self._TOPIC_SKIP_SUBSTRINGS):
            return True
        head = re.split(r'[：:]', name, maxsplit=1)[0].strip()
        return head in self._TOPIC_SKIP_EXACT

    @staticmethod
    def _get_topics_section(text: str) -> str:
        """Return the raw text of the 主要討論話題 section only."""
        lines = []
        in_section = False
        for line in text.split('\n'):
            stripped = line.strip()
            if '主要討論話題' in stripped:
                in_section = True
                continue
            if in_section and (stripped.startswith('###') or stripped.startswith('---')):
                break
            if in_section:
                lines.append(line)
        return '\n'.join(lines)

    def _clean_topic_name(self, name: str) -> str:
        """Strip a leading ordinal (`1. ` / `1、`), a `話題名稱：` label prefix, and
        any trailing colon."""
        name = name.strip()
        name = re.sub(r'^\d+\s*[.、）)]\s*', '', name)  # "1. " / "1、" / "1)"
        name = self._TOPIC_LABEL_PREFIX.sub('', name)
        return name.rstrip('：:').strip()

    def _extract_main_topics(self, text: str) -> list[str]:
        """Extract the main topic headers from 主要討論話題, ignoring sub-bullets.

        Two heading styles appear across podcasts:
          - Numbered-bold (gooaye):          **1. Topic Name**
          - Bullet-bold (yutinghao/zhaohua): *   **Topic Name**  /  1. **Topic Name**

        Numbered-bold headings take priority: when present, flush-left sub-bullets
        like `*   **話題名稱：** ...` are never scraped as topics. Older gooaye
        episodes and the daily shows fall back to the bullet-bold style.
        """
        section = self._get_topics_section(text)
        if not section:
            return []

        # Tier 1 — numbered-bold headings: **1. Topic Name**
        numbered = []
        for line in section.split('\n'):
            match = re.match(r'^\*\*\s*\d+\s*[.、]\s*(.+?)\*\*\s*$', line.strip())
            if not match:
                continue
            name = self._clean_topic_name(match.group(1))
            if name and not self._is_generic_label(name):
                numbered.append(name)
        if numbered:
            return numbered

        # Tier 2 — bullet-bold / number-dot-bold headings (yutinghao, zhaohua, older gooaye)
        topics = []
        for line in section.split('\n'):
            stripped = line.strip()
            is_main_topic = (
                re.match(r'^[-*]\s+\*\*', stripped) or  # * **Topic**
                re.match(r'^\d+\.\s+\*\*', stripped)     # 1. **Topic**
            )
            if not is_main_topic:
                continue
            # Skip indented sub-bullets
            if line.startswith('    ') or line.startswith('\t'):
                continue
            match = re.search(r'\*\*(.+?)\*\*', stripped)
            if not match:
                continue
            topic_name = self._clean_topic_name(match.group(1))
            if topic_name and not self._is_generic_label(topic_name):
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

        # Parse jokes - each starts with a top-level item (bullet or numbered)
        # containing a bold title like **【賓利車與淹水】**
        current_title = ""
        current_parts = {}  # key: 情節/笑點/寓意, value: text

        def _flush_joke():
            if not current_title:
                return
            # Build joke text: title + story + punchline
            parts = []
            parts.append(f"【{current_title}】")
            story = current_parts.get("情節", "")
            punchline = current_parts.get("笑點", "")
            # For short jokes without sub-structure, use any available text
            if not story and not punchline:
                # Grab first non-empty part
                for v in current_parts.values():
                    if v:
                        parts.append(v)
                        break
            else:
                if story:
                    parts.append(story)
                if punchline:
                    parts.append(punchline)
            if len(parts) > 1:
                jokes.append(" ".join(parts))

        for line in section.split('\n'):
            stripped = line.strip()
            if not stripped:
                continue

            # Top-level joke header: bullet or numbered, with bold title
            is_top = (
                re.match(r'^[-*]\s+\*\*', stripped) or
                re.match(r'^\d+\.\s+\*\*', stripped)
            ) and not line.startswith('    ')

            if is_top:
                _flush_joke()
                # Extract title from bold markers like **【賓利車與淹水】**
                title_match = re.search(r'\*\*[【\[]?(.+?)[】\]]?\*\*', stripped)
                current_title = title_match.group(1).rstrip("：:") if title_match else ""
                current_parts = {}
                continue

            # Sub-bullet with label: *   **情節：** content
            sub_match = re.match(r'^[-*]\s+\*\*(.+?)[：:]\*\*\s*(.*)', stripped)
            if sub_match and current_title:
                label = sub_match.group(1).strip()
                content = sub_match.group(2).strip()
                # Strip inner bold markers from content
                content = re.sub(r'\*\*(.+?)\*\*', r'\1', content)
                current_parts[label] = content
                continue

            # Unlabeled sub-bullet content
            if current_title and stripped.startswith(('*', '-')):
                content = re.sub(r'^[-*]\s+', '', stripped)
                content = re.sub(r'\*\*(.+?)\*\*', r'\1', content)
                if content:
                    current_parts.setdefault("_other", "")
                    current_parts["_other"] += " " + content

        _flush_joke()
        return jokes
