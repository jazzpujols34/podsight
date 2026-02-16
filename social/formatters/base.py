"""Base formatter class for social media content."""

import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class SummaryContent:
    """Parsed summary content from AI summary file."""
    episode_id: str
    podcast_name: str
    host: str
    one_liner: str = ""
    topics: list[str] = field(default_factory=list)
    tickers: dict[str, list[str]] = field(default_factory=dict)  # {"美股": ["NVDA"], "台股": ["2330"]}
    quotes: list[str] = field(default_factory=list)
    raw_text: str = ""

    @classmethod
    def from_summary_file(cls, filepath: Path, episode_id: str, podcast_name: str, host: str) -> "SummaryContent":
        """Parse a summary file into structured content."""
        text = filepath.read_text(encoding="utf-8")

        content = cls(
            episode_id=episode_id,
            podcast_name=podcast_name,
            host=host,
            raw_text=text
        )

        # Parse sections
        # One-liner can be on same line (一句話總結：content) or next line (### **一句話總結**\ncontent)
        content.one_liner = cls._extract_one_liner(text)
        content.topics = cls._extract_bullet_list(text, r"主要討論話題")
        content.tickers = cls._extract_tickers(text)
        content.quotes = cls._extract_bullet_list(text, rf"{host}.*?(?:觀點|金句)")

        return content

    @staticmethod
    def _extract_section(text: str, pattern: str) -> str:
        """Extract a single-line section."""
        match = re.search(pattern, text, re.IGNORECASE)
        return match.group(1).strip() if match else ""

    @staticmethod
    def _extract_one_liner(text: str) -> str:
        """Extract one-liner summary, handling various formats."""
        # Try: ### **一句話總結**\ncontent (header on separate line)
        match = re.search(
            r"一句話總結\**\s*\n+([^\n#]+)",
            text, re.IGNORECASE
        )
        if match:
            return match.group(1).strip()

        # Try: 一句話總結：content (inline)
        match = re.search(
            r"一句話總結[：:]\s*(.+?)(?:\n|$)",
            text, re.IGNORECASE
        )
        if match:
            return match.group(1).strip()

        return ""

    @staticmethod
    def _extract_bullet_list(text: str, section_header: str) -> list[str]:
        """Extract bullet points following a section header."""
        # Find section
        pattern = rf"{section_header}.*?\n((?:[-•*]\s*.+\n?)+)"
        match = re.search(pattern, text, re.IGNORECASE | re.DOTALL)
        if not match:
            return []

        # Extract bullets
        bullets = re.findall(r"[-•*]\s*(.+?)(?:\n|$)", match.group(1))
        # Filter out empty, separator-only (---), and header lines
        cleaned = []
        for b in bullets:
            b = b.strip()
            if not b:
                continue
            if re.match(r'^-+$', b):  # Skip --- separators
                continue
            if b.startswith('#'):  # Skip headers
                continue
            cleaned.append(b)
        return cleaned

    @staticmethod
    def _extract_tickers(text: str) -> dict[str, list[str]]:
        """Extract stock tickers by market."""
        tickers = {}

        # Look for ticker section
        section_match = re.search(
            r"(?:提到的)?(?:股票|標的|ETF).*?\n((?:.+\n?)+?)(?=\n\n|\n[#*]|\Z)",
            text, re.IGNORECASE
        )
        if not section_match:
            return tickers

        section = section_match.group(1)

        # Extract by market
        markets = {
            "美股": r"美股[：:]\s*(.+?)(?:\n|$)",
            "台股": r"台股[：:]\s*(.+?)(?:\n|$)",
            "ETF": r"ETF[：:]\s*(.+?)(?:\n|$)",
            "產業": r"(?:產業|族群)[：:]\s*(.+?)(?:\n|$)",
        }

        for market, pattern in markets.items():
            match = re.search(pattern, section, re.IGNORECASE)
            if match:
                # Split by comma, space, or Chinese comma
                symbols = re.split(r"[,，、\s]+", match.group(1))
                tickers[market] = [s.strip() for s in symbols if s.strip()]

        return tickers

    def get_all_tickers(self) -> list[str]:
        """Get all tickers as a flat list."""
        all_tickers = []
        for market_tickers in self.tickers.values():
            all_tickers.extend(market_tickers)
        return all_tickers

    def get_us_tickers(self) -> list[str]:
        """Get US stock tickers (for cashtags)."""
        return self.tickers.get("美股", [])


class BaseFormatter(ABC):
    """Base class for platform-specific formatters."""

    platform: str = "base"

    @abstractmethod
    def format(self, content: SummaryContent) -> dict[str, Any]:
        """Format summary content for the platform.

        Returns a dict that will be saved as {platform}.json
        """
        pass

    def strip_markdown(self, text: str) -> str:
        """Remove markdown formatting from text.

        Social media platforms don't render markdown, so **bold**, ##headers, etc.
        will show as literal characters.
        """
        # Remove horizontal rules first (before they get partially matched)
        text = re.sub(r'^[-*_]{2,}\s*$', '', text, flags=re.MULTILINE)
        text = re.sub(r'^--+$', '', text, flags=re.MULTILINE)

        # Remove headers (### **Header** patterns)
        text = re.sub(r'^#{1,6}\s*\**\s*', '', text, flags=re.MULTILINE)

        # Remove bold/italic markers (including trailing ones)
        text = re.sub(r'\*\*\*(.+?)\*\*\*', r'\1', text)  # ***bold italic***
        text = re.sub(r'\*\*(.+?)\*\*', r'\1', text)      # **bold**
        text = re.sub(r'\*\*', '', text)                   # any remaining **
        text = re.sub(r'(?<!\*)\*(?!\*)', '', text)        # single * (not part of **)
        text = re.sub(r'__(.+?)__', r'\1', text)          # __bold__
        text = re.sub(r'_(.+?)_', r'\1', text)            # _italic_

        # Remove inline code
        text = re.sub(r'`(.+?)`', r'\1', text)

        # Remove links but keep text: [text](url) -> text
        text = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', text)

        # Clean up any remaining stray asterisks at word boundaries
        text = re.sub(r'\s\*+\s', ' ', text)              # isolated asterisks
        text = re.sub(r'\*+$', '', text)                   # trailing asterisks
        text = re.sub(r'^\*+\s*', '', text)                # leading asterisks

        return text.strip()

    def count_chars(self, text: str) -> int:
        """Count characters, treating CJK as 2 chars (Twitter counting)."""
        count = 0
        for char in text:
            if '\u4e00' <= char <= '\u9fff':  # CJK range
                count += 2
            else:
                count += 1
        return count

    def truncate_to_limit(self, text: str, limit: int, suffix: str = "...") -> str:
        """Truncate text to character limit (CJK-aware)."""
        if self.count_chars(text) <= limit:
            return text

        suffix_len = self.count_chars(suffix)
        target = limit - suffix_len

        result = []
        current = 0
        for char in text:
            char_len = 2 if '\u4e00' <= char <= '\u9fff' else 1
            if current + char_len > target:
                break
            result.append(char)
            current += char_len

        return ''.join(result) + suffix
