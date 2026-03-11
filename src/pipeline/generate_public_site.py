#!/usr/bin/env python3
"""
Generate static public site from podcast summaries.
Creates HTML pages for all episodes across all podcasts.
"""

import json
import os
import re
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Tuple

# Paths (project root is parent of src/)
BASE_DIR = Path(__file__).parent.parent.parent
DATA_DIR = BASE_DIR / "data"
OUTPUT_DIR = BASE_DIR / "public-site"

# Podcast configurations
PODCASTS = {
    "gooaye": {
        "name": "股癌 Gooaye",
        "short_name": "股癌",
        "host": "謝孟恭 Melody Hsieh",
        "description": "用輕鬆詼諧的方式，分享投資心法與市場觀察，陪你在股海中找到方向。",
        "badge_text": "投資理財",
        "badge_icon": "trending-up",
        "episode_prefix": "EP",
        "url_format": "number",  # /gooaye/638/
        "theme": "blue",
        "css_vars": """
            --bg-primary: #0a0f1a;
            --bg-secondary: #111827;
            --bg-card: rgba(26, 111, 175, 0.08);
            --bg-card-hover: rgba(26, 111, 175, 0.12);
            --border-subtle: rgba(77, 184, 232, 0.15);
            --border-glow: rgba(77, 184, 232, 0.3);
            --text-primary: #f0f9ff;
            --text-secondary: rgba(240, 249, 255, 0.75);
            --text-muted: rgba(240, 249, 255, 0.5);
            --accent-primary: #4DB8E8;
            --accent-secondary: #1A6FAF;
            --accent-tertiary: #F5A623;
            --accent-glow: rgba(77, 184, 232, 0.4);
            --accent-gradient: linear-gradient(135deg, #1A6FAF 0%, #4DB8E8 50%, #F5A623 100%);
            --accent-bg: rgba(77, 184, 232, 0.12);
            --accent-border: rgba(77, 184, 232, 0.25);
        """,
    },
    "yutinghao": {
        "name": "游庭皓的財經皓角",
        "short_name": "財經皓角",
        "host": "游庭皓",
        "description": "深入淺出的財經分析，結合時事與數據，帶你看懂市場背後的邏輯。",
        "badge_text": "每日財經",
        "badge_icon": "bar-chart-2",
        "episode_prefix": "",
        "url_format": "date",  # /yutinghao/2025-02-20/
        "theme": "minimal",
        "css_vars": """
            --bg-primary: #0f0f0f;
            --bg-secondary: #1a1a1a;
            --bg-card: rgba(26, 26, 26, 0.8);
            --bg-card-hover: rgba(40, 40, 40, 0.9);
            --border-subtle: rgba(255, 255, 255, 0.08);
            --border-glow: rgba(255, 255, 255, 0.15);
            --text-primary: #ffffff;
            --text-secondary: rgba(255, 255, 255, 0.7);
            --text-muted: rgba(255, 255, 255, 0.4);
            --accent-primary: #ffffff;
            --accent-secondary: #e0e0e0;
            --accent-tertiary: #a0a0a0;
            --accent-glow: rgba(255, 255, 255, 0.2);
            --accent-gradient: linear-gradient(135deg, #ffffff 0%, #e0e0e0 100%);
            --accent-bg: rgba(255, 255, 255, 0.08);
            --accent-border: rgba(255, 255, 255, 0.2);
        """,
    },
    "zhaohua": {
        "name": "兆華與股惑仔",
        "short_name": "兆華",
        "host": "李兆華",
        "description": "結合專業與生活化的角度，帶你掌握台股脈動與投資機會。",
        "badge_text": "台股分析",
        "badge_icon": "mic",
        "episode_prefix": "EP",
        "url_format": "number",  # /zhaohua/1010/
        "theme": "warm",
        "css_vars": """
            --bg-primary: #1a1512;
            --bg-secondary: #241d18;
            --bg-card: rgba(244, 169, 127, 0.08);
            --bg-card-hover: rgba(244, 169, 127, 0.12);
            --border-subtle: rgba(244, 169, 127, 0.15);
            --border-glow: rgba(245, 200, 66, 0.3);
            --text-primary: #fff5f0;
            --text-secondary: rgba(255, 245, 240, 0.75);
            --text-muted: rgba(255, 245, 240, 0.5);
            --accent-primary: #F4A97F;
            --accent-secondary: #F5C842;
            --accent-tertiary: #4A90D9;
            --accent-glow: rgba(244, 169, 127, 0.4);
            --accent-gradient: linear-gradient(135deg, #F4A97F 0%, #F5C842 50%, #FFCDB2 100%);
            --accent-bg: rgba(244, 169, 127, 0.12);
            --accent-border: rgba(244, 169, 127, 0.25);
        """,
    },
}


def parse_rfc_date(date_str: str) -> Optional[str]:
    """Parse RFC 2822 date format to YYYY-MM-DD."""
    if not date_str:
        return None
    try:
        # Format: "Wed, 25 Feb 2026 08:29:59 GMT"
        from email.utils import parsedate_to_datetime
        dt = parsedate_to_datetime(date_str)
        return dt.strftime("%Y-%m-%d")
    except:
        return None


def get_freshness_label(date_str: str) -> Tuple[str, str]:
    """Get freshness label and CSS class for a date string.
    Returns (label, css_class) or (None, None) if not recent."""
    try:
        today = datetime.now().date()

        # Try to parse date
        if re.match(r"\d{4}-\d{2}-\d{2}", date_str):
            ep_date = datetime.strptime(date_str, "%Y-%m-%d").date()
        else:
            return None, None

        days_ago = (today - ep_date).days

        if days_ago == 0:
            return "今天", "fresh-today"
        elif days_ago == 1:
            return "昨天", "fresh-yesterday"
        elif days_ago <= 7:
            return "本週", "fresh-week"
        else:
            return None, None
    except:
        return None, None


def extract_episode_date(episode_id: str, podcast_id: str, filename: str = "") -> Optional[str]:
    """Extract or estimate episode date in YYYY-MM-DD format."""
    if podcast_id == "yutinghao":
        # Already in date format
        return episode_id

    # For numbered podcasts, try to get from filename or estimate
    # We'll use file modification time as fallback
    if filename:
        match = re.match(r"(\d{4})_(\d{1,2})_(\d{1,2})_", filename)
        if match:
            year, month, day = match.groups()
            return f"{year}-{int(month):02d}-{int(day):02d}"

    return None


def normalize_stock_symbol(symbol: str) -> str:
    """Normalize stock symbol for consistent indexing."""
    # Remove parentheses content for matching
    clean = re.sub(r"\s*\([^)]+\)", "", symbol).strip()
    return clean.lower()


def get_sort_key(filename: str, podcast_id: str):
    """Get sort key for a summary file. Returns tuple for proper sorting."""
    name = filename.replace("_summary.txt", "")

    # For EP-based podcasts (gooaye, zhaohua), sort by episode number
    if podcast_id in ["gooaye", "zhaohua"]:
        match = re.search(r"EP?(\d+)", name, re.IGNORECASE)
        if match:
            return (0, int(match.group(1)))
        return (1, name)

    # For date-based podcasts (yutinghao), parse the date
    # Format: 2026_2_24_二_... or _市場觀察_...
    match = re.match(r"(\d{4})_(\d{1,2})_(\d{1,2})_", name)
    if match:
        year, month, day = int(match.group(1)), int(match.group(2)), int(match.group(3))
        return (0, year, month, day)

    # Files starting with _ (like _市場觀察_) - put at the end
    if name.startswith("_"):
        return (1, 0, 0, 0, name)

    return (2, 0, 0, 0, name)


def strip_markdown(text: str) -> str:
    """Remove markdown formatting from text."""
    if not text:
        return ""
    # Remove bold markers
    text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)
    # Remove italic markers
    text = re.sub(r"\*(.+?)\*", r"\1", text)
    # Remove bullet points at start of lines
    text = re.sub(r"^\s*[\*\-•]\s*", "", text, flags=re.MULTILINE)
    # Remove nested bullet points
    text = re.sub(r"\n\s*[\*\-•]\s*", " ", text)
    # Remove markdown links [text](url)
    text = re.sub(r"\[([^\]]+)\]\([^\)]+\)", r"\1", text)
    # Remove inline code
    text = re.sub(r"`([^`]+)`", r"\1", text)
    # Remove extra whitespace
    text = re.sub(r"\s+", " ", text)
    # Remove leading/trailing whitespace
    text = text.strip()
    return text


def parse_summary(content: str) -> dict:
    """Parse markdown summary into structured sections."""
    sections = {
        "tldr": "",
        "topics": [],
        "strategies": [],
        "stocks": [],
        "quotes": [],
        "risks": [],
        "humor": [],
        "conclusion": "",
    }

    # Extract TLDR (一句話總結) - handle ### **Title** or ### Title formats
    tldr_match = re.search(r"###\s*\*?\*?一句話總結\*?\*?\s*\n+(.+?)(?=\n---|\n###|$)", content, re.DOTALL)
    if tldr_match:
        sections["tldr"] = strip_markdown(tldr_match.group(1))

    # Extract topics (主要討論話題) - handle ### **Title** or ### Title formats
    topics_match = re.search(
        r"###\s*\*?\*?主要討論話題\*?\*?\s*\n+(.+?)(?=\n---|\n###)", content, re.DOTALL
    )
    if topics_match:
        topics_text = topics_match.group(1)
        topic_blocks = []

        # Format 1: *   **Title**\n    Content (bullet with bold title, content until next topic)
        # This handles: *   **台日美股表現兩極化**\n    台股與日股...
        bullet_topics = re.findall(
            r"\*\s+\*\*([^*\n]+)\*\*\s*\n([\s\S]+?)(?=\n\*\s+\*\*|\n---|\n###|$)",
            topics_text,
        )
        if bullet_topics:
            for title, content_text in bullet_topics:
                topic_blocks.append((title, content_text))

        # Format 2: **1. Title**\nContent (numbered format)
        if not topic_blocks:
            topic_blocks = re.findall(
                r"\*\*(\d+\.\s*[^*\n]+)\*\*\s*\n(.+?)(?=\n\n\*\*\d+\.|\n---|\n###|$)",
                topics_text,
                re.DOTALL,
            )

        # Format 3: **話題名稱：XXX** with 詳細說明
        if not topic_blocks:
            topic_blocks = re.findall(
                r"\*\*(?:話題名稱：)?([^*\n：:]+)[：:]?\*\*[：:\s]*\n?\s*(?:\*\s*\*\*詳細說明：?\*\*\s*)?(.+?)(?=\n\s*\*\s*\*\*[^詳相利]|\n\s*---|\n\s*###|$)",
                topics_text,
                re.DOTALL,
            )

        for title, content_text in topic_blocks:
            # Clean up content - remove related stocks section and bullet sub-items
            content_clean = re.sub(r"\s*\*?\s*\*?\*?相關標的.*", "", content_text, flags=re.DOTALL)
            content_clean = re.sub(r"\s*\*\s*\*\*利[多空]因素.*", "", content_clean, flags=re.DOTALL)
            content_clean = re.sub(r"\s*\*\s*\*\*市場背景.*", "", content_clean, flags=re.DOTALL)
            content_clean = strip_markdown(content_clean)
            if title and content_clean and len(content_clean) > 20:
                sections["topics"].append({"title": strip_markdown(title), "content": content_clean})

    # Extract strategies (操作心法) - handle multiple section names
    strategies_match = re.search(
        r"###\s*\*?\*?(?:MK\s*的\s*)?操作心法[與和]?作法?\*?\*?\s*\n+(.+?)(?=\n---|\n###)",
        content,
        re.DOTALL,
    )
    if not strategies_match:
        strategies_match = re.search(
            r"###\s*\*?\*?(?:兆華的)?操作建議\*?\*?\s*\n+(.+?)(?=\n---|\n###)", content, re.DOTALL
        )
    if not strategies_match:
        # Try zhaohua format: 本集來賓與高手觀點
        strategies_match = re.search(
            r"###\s*\*?\*?本集來賓與高手觀點\*?\*?\s*\n+(.+?)(?=\n---|\n###)", content, re.DOTALL
        )
    if not strategies_match:
        # Try yutinghao format: 財經觀點與分析
        strategies_match = re.search(
            r"###\s*\*?\*?財經觀點與分析\*?\*?\s*\n+(.+?)(?=\n---|\n###)", content, re.DOTALL
        )
    if strategies_match:
        strategies_text = strategies_match.group(1)
        strategy_items = []

        # Format 1: Numbered list with nested bullets
        # 1.  **Title**\n    Content\n    *   **Sub:** details
        numbered_items = re.findall(
            r"(\d+)\.\s+\*\*([^*\n]+)\*\*\s*\n((?:[ \t]+.*?\n?)*?)(?=\n\d+\.|\n---|\n###|$)",
            strategies_text,
            re.MULTILINE,
        )
        if numbered_items:
            for num, title, content_text in numbered_items:
                # Parse nested sub-bullets within content
                sub_items = re.findall(r"\*\s+\*\*([^*]+)\*\*[：:]\s*(.+?)(?=\n\s*\*\s+\*\*|\n\d+\.|\n---|$)", content_text, re.DOTALL)
                if sub_items:
                    # Build full content with sub-items
                    full_content = []
                    for sub_title, sub_content in sub_items:
                        full_content.append(f"{strip_markdown(sub_title)}：{strip_markdown(sub_content)}")
                    strategy_items.append((title, "\n".join(full_content)))
                else:
                    # No sub-items, just use content directly
                    strategy_items.append((title, content_text))

        # Format 2: Bullet points with **title:** content
        if not strategy_items:
            strategy_items = re.findall(
                r"\*\s*\*\*([^*]+)\*\*[：:]\s*(.+?)(?=\n\*\s*\*\*|\n---|\n###|$)",
                strategies_text,
                re.DOTALL,
            )

        if strategy_items:
            for title, content_text in strategy_items:
                full_text = f"{strip_markdown(title)}：{strip_markdown(content_text)}"
                if full_text and len(full_text) > 10:
                    sections["strategies"].append(full_text)
        else:
            # Fallback: simple bullet points
            bullets = re.findall(r"[•\-\*]\s*(.+?)(?=\n[•\-\*]|\n\n|$)", strategies_text, re.DOTALL)
            sections["strategies"] = [strip_markdown(b) for b in bullets if b.strip() and len(b.strip()) > 10]

    # Extract stocks (提到的股票) - handle ### **Title** or ### Title formats
    stocks_match = re.search(
        r"###\s*\*?\*?提到的股票.*?\*?\*?\s*\n+(.+?)(?=\n---|\n###)", content, re.DOTALL
    )
    if stocks_match:
        stocks_text = stocks_match.group(1)
        # Parse stock entries: **symbol** - name or * **symbol**: name (支援 - 和 ：)
        stock_items = re.findall(
            r"\*?\s*\*\*([^*]+)\*\*\s*[\-–：:]\s*(.+?)(?=\n|$)", stocks_text
        )
        if stock_items:
            for symbol, name in stock_items:
                # Clean up - remove trailing punctuation and extra info
                name_clean = re.sub(r"[。，,].*", "", name).strip()
                name_clean = strip_markdown(name_clean)
                symbol_clean = strip_markdown(symbol)
                if symbol_clean:
                    sections["stocks"].append({"symbol": symbol_clean, "name": name_clean})

    # Extract quotes (金句) - handle ### **Title** or ### Title formats and 觀點金句
    quotes_match = re.search(
        r"###\s*\*?\*?(?:謝孟恭|兆華)?.*?(?:的\s*)?(?:觀點[或與]?)?金句.*?\*?\*?\s*\n+(.+?)(?=\n---|\n###|$)",
        content,
        re.DOTALL,
    )
    if quotes_match:
        quotes_text = quotes_match.group(1)
        # Parse quotes - look for 「quote」 or **title:** "quote" patterns
        # First try 「」quotes
        quote_items = re.findall(r"[「]([^」]+)[」]", quotes_text)
        if quote_items:
            sections["quotes"] = [strip_markdown(q) for q in quote_items if len(q.strip()) > 10]
        else:
            # Try bullet format with quotes
            bullets = re.findall(r"\*\s*\*\*[^*]+\*\*[：:]\s*[「「]([^」」]+)[」」]", quotes_text)
            if bullets:
                sections["quotes"] = [strip_markdown(q) for q in bullets if len(q.strip()) > 10]
            else:
                # Try simple bullet format
                quote_items = re.findall(r"[•\-\*]\s*(.+?)(?=\n[•\-\*]|\n\n|$)", quotes_text)
                sections["quotes"] = [strip_markdown(q) for q in quote_items if len(q.strip()) > 10]

    # Extract risks (風險提醒) or 市場展望與操作建議 - handle ### **Title** or ### Title formats
    risks_match = re.search(r"###\s*\*?\*?風險提醒\*?\*?\s*\n+(.+?)(?=\n---|\n###|$)", content, re.DOTALL)
    if not risks_match:
        # Try zhaohua format: 市場展望與操作建議
        risks_match = re.search(r"###\s*\*?\*?市場展望與操作建議\*?\*?\s*\n+(.+?)(?=\n---|\n###|$)", content, re.DOTALL)
    if risks_match:
        risks_text = risks_match.group(1)
        # Parse risks - look for **title:** content or simple bullets
        risk_items = re.findall(r"\*\s*\*\*([^*]+)\*\*[：:]\s*(.+?)(?=\n\*\s*\*\*|\n\n|$)", risks_text, re.DOTALL)
        if risk_items:
            for title, content_text in risk_items:
                full_text = f"{strip_markdown(title)}：{strip_markdown(content_text)}"
                if full_text:
                    sections["risks"].append(full_text)
        else:
            # Simple bullet format
            risk_items = re.findall(r"[•\-\*]\s*(.+?)(?=\n[•\-\*]|\n\n|$)", risks_text, re.DOTALL)
            sections["risks"] = [strip_markdown(r) for r in risk_items if r.strip() and len(r.strip()) > 10]

    # Extract humor (冷笑話 / 幽默金句)
    humor_match = re.search(
        r"###\s*\*?\*?冷笑話\s*[/／]\s*幽默金句\*?\*?\s*\n+(.+?)(?=\n---|\n###|$)", content, re.DOTALL
    )
    if humor_match:
        humor_text = humor_match.group(1)
        # Extract all bold-labeled bullet items, then parse quotes from each
        # Handles: **Label**：「Q」, **Label：**「Q」, **Label**：plain text
        bullets = re.findall(
            r"\*\s+\*\*([^*]+?)[：:]?\*\*[：:]?\s*(.+?)(?=\n\*\s+\*\*|\n---|$)",
            humor_text, re.DOTALL
        )
        for label, content_text in bullets:
            label = strip_markdown(label.rstrip("：:"))
            content_text = content_text.strip()
            # Try to extract quote in「」brackets
            quote_match = re.search(r"[「「]([^」」]+)[」」]", content_text)
            # Try to extract context in（）brackets
            context_match = re.search(r"（([^）]+)）", content_text)
            item = {
                "label": label,
                "quote": strip_markdown(quote_match.group(1) if quote_match else content_text)
            }
            if context_match:
                item["context"] = strip_markdown(context_match.group(1))
            sections["humor"].append(item)

    # Extract conclusion (本集結論)
    conclusion_match = re.search(
        r"\*\*本集結論[：:]\*\*\s*(.+?)(?=\n\n|$)", content, re.DOTALL
    )
    if conclusion_match:
        sections["conclusion"] = strip_markdown(conclusion_match.group(1))

    return sections


def get_episode_id(filename: str, podcast: str) -> str:
    """Extract episode ID from filename."""
    if podcast == "yutinghao":
        # Format: 2026_1_30_五_微軟暴跌...
        match = re.match(r"(\d{4})_(\d{1,2})_(\d{1,2})_", filename)
        if match:
            year, month, day = match.groups()
            return f"{year}-{int(month):02d}-{int(day):02d}"
    else:
        # Format: EP0630_summary.txt
        match = re.search(r"EP(\d+)", filename)
        if match:
            return match.group(1)
    return None


def get_episode_title(filename: str, podcast: str) -> str:
    """Extract episode title from filename."""
    if podcast == "yutinghao":
        # Format: 2026_1_30_五_微軟暴跌近10_...
        parts = filename.replace("_summary.txt", "").split("_")
        if len(parts) > 4:
            # Join title parts, replace underscores with spaces
            title = " ".join(parts[4:])
            # Clean up
            title = title.replace("_", " ").replace("  ", " ")
            # Truncate if too long
            if len(title) > 50:
                title = title[:50] + "..."
            return title
    return None


def generate_episode_html(
    podcast_id: str, episode_id: str, sections: dict, episode_info: dict,
    prev_episode: Optional[dict] = None, next_episode: Optional[dict] = None
) -> str:
    """Generate HTML for an episode page."""
    config = PODCASTS[podcast_id]

    # Build title
    if config["episode_prefix"]:
        display_id = f"{config['episode_prefix']}{episode_id}"
    else:
        display_id = episode_id

    # Get episode date
    if podcast_id == "yutinghao":
        date_display = episode_id  # Already in YYYY-MM-DD format
    else:
        # Try to get from episode_info
        date_display = episode_info.get("date", "")

    # Build prev/next navigation HTML
    nav_html = ""
    if prev_episode or next_episode:
        prev_btn = ""
        next_btn = ""
        if prev_episode:
            prev_id = prev_episode["id"]
            prev_title = prev_episode.get("title", f"{config['episode_prefix']}{prev_id}")[:30]
            prev_btn = f'''<a href="/{podcast_id}/{prev_id}/" class="ep-nav-btn ep-nav-prev">
                <i data-lucide="chevron-left"></i>
                <span class="ep-nav-label">上一集</span>
                <span class="ep-nav-title">{html_escape(prev_title)}</span>
            </a>'''
        else:
            prev_btn = '<div class="ep-nav-btn ep-nav-disabled"></div>'

        if next_episode:
            next_id = next_episode["id"]
            next_title = next_episode.get("title", f"{config['episode_prefix']}{next_id}")[:30]
            next_btn = f'''<a href="/{podcast_id}/{next_id}/" class="ep-nav-btn ep-nav-next">
                <span class="ep-nav-label">下一集</span>
                <span class="ep-nav-title">{html_escape(next_title)}</span>
                <i data-lucide="chevron-right"></i>
            </a>'''
        else:
            next_btn = '<div class="ep-nav-btn ep-nav-disabled"></div>'

        nav_html = f'''<nav class="episode-nav">{prev_btn}{next_btn}</nav>'''

    # Build TOC items based on available sections
    toc_items = []
    if sections["tldr"]:
        toc_items.append(("tldr", "摘要"))
    if sections["topics"]:
        toc_items.append(("topics", "話題"))
    if sections["strategies"]:
        toc_items.append(("strategies", "心法"))
    if sections["stocks"]:
        toc_items.append(("stocks", "股票"))
    if sections["quotes"]:
        toc_items.append(("quotes", "金句"))
    if sections["humor"]:
        toc_items.append(("humor", "幽默"))
    if sections["risks"]:
        toc_items.append(("risks", "風險"))
    if sections["conclusion"]:
        toc_items.append(("conclusion", "結論"))

    toc_html = ""
    if len(toc_items) > 2:
        toc_links = "".join([f'<a href="#{id}" class="toc-link" data-section="{id}">{label}</a>' for id, label in toc_items])
        toc_html = f'''<nav class="toc">{toc_links}</nav>'''

    # Build topics HTML
    topics_html = ""
    for i, topic in enumerate(sections["topics"][:5], 1):
        topics_html += f"""
                    <div class="topic-card">
                        <div class="topic-number">TOPIC {i:02d}</div>
                        <div class="topic-title">{html_escape(topic['title'])}</div>
                        <div class="topic-content">{html_escape(topic['content'])}</div>
                    </div>"""

    # Build strategies HTML
    strategies_html = ""
    icons = ["target", "layers", "shield", "eye", "percent"]
    for i, strategy in enumerate(sections["strategies"][:5]):
        icon = icons[i % len(icons)]
        strategies_html += f"""
                    <div class="strategy-card">
                        <div class="strategy-icon">
                            <i data-lucide="{icon}"></i>
                        </div>
                        <div class="strategy-text">{html_escape(strategy)}</div>
                    </div>"""

    # Build stocks HTML (clickable links to stock search)
    stocks_html = ""
    for stock in sections["stocks"][:12]:
        stock_query = html_escape(stock['symbol'].split('(')[0].strip())
        stocks_html += f"""
                    <a href="/stocks/?q={stock_query}" class="stock-tag">
                        <span class="stock-symbol">{html_escape(stock['symbol'])}</span>
                        <span class="stock-name">{html_escape(stock['name'])}</span>
                    </a>"""

    # Build quotes HTML
    quotes_html = ""
    for quote in sections["quotes"][:5]:
        quotes_html += f"""
                    <div class="quote-card">
                        <span class="quote-icon"><i data-lucide="quote"></i></span>
                        <p class="quote-text">{html_escape(quote)}</p>
                    </div>"""

    # Build risks HTML
    risks_html = ""
    for risk in sections["risks"][:5]:
        risks_html += f"""
                    <div class="risk-item">
                        <span class="risk-icon"><i data-lucide="alert-circle"></i></span>
                        <span class="risk-text">{html_escape(risk)}</span>
                    </div>"""

    # Build humor HTML
    humor_html = ""
    for item in sections["humor"][:6]:
        context_html = f'<span class="humor-context">（{html_escape(item.get("context", ""))}）</span>' if item.get("context") else ""
        humor_html += f"""
                    <div class="humor-card">
                        <span class="humor-label">{html_escape(item['label'])}</span>
                        <p class="humor-quote">「{html_escape(item['quote'])}」{context_html}</p>
                    </div>"""

    # Episode title for display
    episode_title = episode_info.get("title", f"{display_id}")
    if episode_title.startswith("EP") and "|" in episode_title:
        # Clean up gooaye titles like "EP638 | 🐈‍⬛"
        episode_title = episode_title.split("|")[0].strip()

    html = f"""<!DOCTYPE html>
<html lang="zh-TW">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{display_id} - {config['short_name']} - PodSight</title>
    <meta name="description" content="{config['name']} {display_id} AI 智慧摘要">

    <!-- Open Graph -->
    <meta property="og:title" content="{display_id} - {config['short_name']} - PodSight 聲見">
    <meta property="og:description" content="{config['name']} {display_id} AI 智慧摘要">
    <meta property="og:image" content="/assets/og-image.png">
    <meta property="og:type" content="article">
    <meta name="twitter:card" content="summary_large_image">

    <!-- Favicon -->
    <link rel="icon" type="image/jpeg" href="/assets/PodSight-Logo-cropped.jpeg">

    <!-- Fonts -->
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;500;600;700;800&family=Noto+Sans+TC:wght@300;400;500;700&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">

    <!-- Lucide Icons -->
    <script src="https://unpkg.com/lucide@latest/dist/umd/lucide.min.js"></script>

    <style>
        :root {{
            {config['css_vars']}
            --glass-blur: 20px;
            --transition-smooth: cubic-bezier(0.4, 0, 0.2, 1);
        }}

        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}

        html {{
            scroll-behavior: smooth;
        }}

        body {{
            font-family: 'Noto Sans TC', 'Outfit', sans-serif;
            background: var(--bg-primary);
            color: var(--text-primary);
            min-height: 100vh;
            overflow-x: hidden;
            line-height: 1.8;
        }}

        .progress-bar {{
            position: fixed;
            top: 0;
            left: 0;
            height: 3px;
            background: var(--accent-gradient);
            z-index: 1000;
            transition: width 0.1s linear;
        }}

        .bg-ambient {{
            position: fixed;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            pointer-events: none;
            z-index: 0;
            background:
                radial-gradient(ellipse at top right, var(--accent-glow) 0%, transparent 50%),
                radial-gradient(ellipse at bottom left, rgba(255,255,255,0.02) 0%, transparent 50%);
        }}

        .container {{
            position: relative;
            z-index: 10;
            max-width: 800px;
            margin: 0 auto;
            padding: 0 24px;
        }}

        .nav {{
            padding: 24px 0;
            display: flex;
            align-items: center;
            justify-content: space-between;
        }}

        .nav-back {{
            display: flex;
            align-items: center;
            gap: 8px;
            color: var(--text-secondary);
            text-decoration: none;
            font-size: 0.9rem;
            transition: color 0.2s;
        }}

        .nav-back:hover {{
            color: var(--accent-primary);
        }}

        .nav-back svg {{
            width: 18px;
            height: 18px;
        }}

        .nav-logo {{
            display: flex;
            align-items: center;
            gap: 8px;
            text-decoration: none;
            color: inherit;
        }}

        .nav-logo-icon {{
            width: 32px;
            height: 32px;
            border-radius: 8px;
            overflow: hidden;
        }}

        .nav-logo-icon img {{
            width: 100%;
            height: 100%;
            object-fit: cover;
        }}

        .nav-logo-text {{
            font-family: 'Outfit', sans-serif;
            font-size: 1.1rem;
            font-weight: 600;
        }}

        .episode-header {{
            padding: 40px 0 60px;
            border-bottom: 1px solid var(--border-subtle);
        }}

        .episode-meta {{
            display: flex;
            align-items: center;
            gap: 16px;
            margin-bottom: 20px;
            flex-wrap: wrap;
        }}

        .episode-badge {{
            display: inline-flex;
            align-items: center;
            gap: 6px;
            padding: 6px 14px;
            background: var(--accent-bg);
            border: 1px solid var(--accent-border);
            border-radius: 100px;
            font-size: 0.85rem;
            color: var(--accent-primary);
        }}

        .episode-badge svg {{
            width: 14px;
            height: 14px;
        }}

        .episode-date {{
            font-family: 'JetBrains Mono', monospace;
            font-size: 0.85rem;
            color: var(--text-muted);
        }}

        .episode-header h1 {{
            font-family: 'Outfit', sans-serif;
            font-size: clamp(2rem, 5vw, 3rem);
            font-weight: 700;
            margin-bottom: 16px;
            letter-spacing: -0.02em;
            line-height: 1.2;
            background: var(--accent-gradient);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            background-clip: text;
        }}

        .episode-subtitle {{
            font-size: 1.1rem;
            color: var(--text-secondary);
            line-height: 1.7;
        }}

        .share-buttons {{
            display: flex;
            gap: 12px;
            margin-top: 24px;
        }}

        .share-btn {{
            display: flex;
            align-items: center;
            gap: 8px;
            padding: 10px 18px;
            background: transparent;
            border: 1px solid var(--border-subtle);
            border-radius: 8px;
            color: var(--text-secondary);
            font-size: 0.9rem;
            cursor: pointer;
            transition: all 0.2s;
            text-decoration: none;
        }}

        .share-btn:hover {{
            border-color: var(--accent-primary);
            color: var(--accent-primary);
            background: var(--accent-bg);
        }}

        .share-btn svg {{
            width: 16px;
            height: 16px;
        }}

        .listen-btn {{
            border-color: var(--accent-primary);
            color: var(--accent-primary);
            background: var(--accent-bg);
        }}

        .listen-btn:hover {{
            background: var(--accent-primary);
            color: #fff;
        }}

        .content {{
            padding: 60px 0;
        }}

        .section {{
            margin-bottom: 56px;
        }}

        .section-header {{
            display: flex;
            align-items: center;
            gap: 12px;
            margin-bottom: 24px;
        }}

        .section-icon {{
            width: 40px;
            height: 40px;
            background: var(--accent-bg);
            border: 1px solid var(--accent-border);
            border-radius: 10px;
            display: flex;
            align-items: center;
            justify-content: center;
            color: var(--accent-primary);
        }}

        .section-icon svg {{
            width: 20px;
            height: 20px;
        }}

        .section-title {{
            font-family: 'Outfit', sans-serif;
            font-size: 1.4rem;
            font-weight: 600;
            color: var(--text-primary);
        }}

        .tldr-box {{
            background: var(--accent-bg);
            border: 1px solid var(--accent-border);
            border-radius: 16px;
            padding: 28px;
            margin-bottom: 48px;
        }}

        .tldr-label {{
            font-size: 0.75rem;
            font-weight: 600;
            text-transform: uppercase;
            letter-spacing: 0.15em;
            color: var(--accent-primary);
            margin-bottom: 12px;
        }}

        .tldr-text {{
            font-size: 1.25rem;
            font-weight: 500;
            line-height: 1.6;
            color: var(--text-primary);
        }}

        .topic-list {{
            display: flex;
            flex-direction: column;
            gap: 16px;
        }}

        .topic-card {{
            background: var(--bg-card);
            border: 1px solid var(--border-subtle);
            border-radius: 12px;
            padding: 24px;
            transition: all 0.2s var(--transition-smooth);
        }}

        .topic-card:hover {{
            border-color: var(--accent-border);
            background: var(--bg-card-hover);
        }}

        .topic-number {{
            font-family: 'JetBrains Mono', monospace;
            font-size: 0.75rem;
            font-weight: 600;
            color: var(--accent-secondary);
            margin-bottom: 8px;
        }}

        .topic-title {{
            font-weight: 600;
            font-size: 1.1rem;
            margin-bottom: 10px;
            color: var(--text-primary);
        }}

        .topic-content {{
            color: var(--text-secondary);
            font-size: 0.95rem;
            line-height: 1.8;
        }}

        .strategy-list {{
            display: flex;
            flex-direction: column;
            gap: 12px;
        }}

        .strategy-card {{
            display: flex;
            align-items: flex-start;
            gap: 16px;
            padding: 20px;
            background: var(--bg-card);
            border: 1px solid var(--border-subtle);
            border-radius: 10px;
            transition: all 0.2s;
        }}

        .strategy-card:hover {{
            border-color: var(--accent-border);
        }}

        .strategy-icon {{
            width: 32px;
            height: 32px;
            background: var(--accent-bg);
            border-radius: 8px;
            display: flex;
            align-items: center;
            justify-content: center;
            color: var(--accent-secondary);
            flex-shrink: 0;
        }}

        .strategy-icon svg {{
            width: 16px;
            height: 16px;
        }}

        .strategy-text {{
            color: var(--text-secondary);
            font-size: 0.95rem;
            line-height: 1.7;
        }}

        .stock-grid {{
            display: flex;
            flex-wrap: wrap;
            gap: 12px;
        }}

        .stock-tag {{
            display: flex;
            align-items: center;
            gap: 8px;
            padding: 12px 18px;
            background: var(--bg-card);
            border: 1px solid var(--border-subtle);
            border-radius: 10px;
            transition: all 0.2s;
        }}

        .stock-tag:hover {{
            border-color: var(--accent-primary);
            background: var(--accent-bg);
        }}

        .stock-symbol {{
            font-family: 'JetBrains Mono', monospace;
            font-weight: 600;
            font-size: 0.9rem;
            color: var(--accent-primary);
        }}

        .stock-name {{
            color: var(--text-muted);
            font-size: 0.85rem;
        }}

        .quote-list {{
            display: flex;
            flex-direction: column;
            gap: 20px;
        }}

        .quote-card {{
            position: relative;
            padding: 24px 24px 24px 32px;
            background: var(--bg-card);
            border: 1px solid var(--border-subtle);
            border-left: 3px solid var(--accent-primary);
            border-radius: 0 12px 12px 0;
        }}

        .quote-text {{
            font-size: 1.1rem;
            font-style: italic;
            line-height: 1.8;
            color: var(--text-primary);
        }}

        .quote-icon {{
            position: absolute;
            top: 16px;
            right: 16px;
            color: var(--accent-bg);
        }}

        .quote-icon svg {{
            width: 24px;
            height: 24px;
        }}

        .humor-list {{
            display: flex;
            flex-direction: column;
            gap: 16px;
        }}

        .humor-card {{
            padding: 20px 24px;
            background: var(--bg-card);
            border: 1px solid var(--border-subtle);
            border-radius: 12px;
            transition: all 0.2s;
        }}

        .humor-card:hover {{
            border-color: var(--accent-border);
            background: var(--bg-card-hover);
        }}

        .humor-label {{
            display: inline-block;
            font-size: 0.75rem;
            font-weight: 600;
            text-transform: uppercase;
            letter-spacing: 0.05em;
            color: var(--accent-secondary);
            background: var(--accent-bg);
            padding: 4px 10px;
            border-radius: 6px;
            margin-bottom: 12px;
        }}

        .humor-quote {{
            font-size: 1rem;
            line-height: 1.8;
            color: var(--text-primary);
        }}

        .humor-context {{
            display: block;
            margin-top: 8px;
            font-size: 0.85rem;
            color: var(--text-muted);
            font-style: italic;
        }}

        .risk-list {{
            display: flex;
            flex-direction: column;
            gap: 12px;
        }}

        .risk-item {{
            display: flex;
            align-items: flex-start;
            gap: 14px;
            padding: 18px;
            background: rgba(239, 68, 68, 0.08);
            border: 1px solid rgba(239, 68, 68, 0.2);
            border-radius: 10px;
        }}

        .risk-icon {{
            color: #ef4444;
            flex-shrink: 0;
            margin-top: 2px;
        }}

        .risk-icon svg {{
            width: 18px;
            height: 18px;
        }}

        .risk-text {{
            color: var(--text-secondary);
            font-size: 0.95rem;
            line-height: 1.7;
        }}

        .conclusion-box {{
            display: flex;
            gap: 20px;
            padding: 28px;
            background: linear-gradient(135deg, var(--accent-bg) 0%, rgba(255,255,255,0.03) 100%);
            border: 1px solid var(--accent-border);
            border-radius: 16px;
        }}

        .conclusion-icon {{
            width: 48px;
            height: 48px;
            background: var(--accent-bg);
            border: 1px solid var(--accent-border);
            border-radius: 12px;
            display: flex;
            align-items: center;
            justify-content: center;
            color: var(--accent-primary);
            flex-shrink: 0;
        }}

        .conclusion-icon svg {{
            width: 24px;
            height: 24px;
        }}

        .conclusion-content {{
            flex: 1;
        }}

        .conclusion-label {{
            font-size: 0.75rem;
            font-weight: 600;
            text-transform: uppercase;
            letter-spacing: 0.15em;
            color: var(--accent-primary);
            margin-bottom: 8px;
        }}

        .conclusion-text {{
            font-size: 1.1rem;
            line-height: 1.8;
            color: var(--text-primary);
        }}

        .footer {{
            padding: 40px 0;
            text-align: center;
            border-top: 1px solid var(--border-subtle);
        }}

        .footer-text {{
            font-size: 0.85rem;
            color: var(--text-muted);
        }}

        .footer-text a {{
            color: var(--accent-primary);
            text-decoration: none;
        }}

        /* Episode Navigation */
        .episode-nav {{
            display: flex;
            justify-content: space-between;
            gap: 16px;
            margin-top: 32px;
            padding-top: 32px;
            border-top: 1px solid var(--border-subtle);
        }}

        .ep-nav-btn {{
            display: flex;
            align-items: center;
            gap: 12px;
            padding: 16px 20px;
            background: var(--bg-card);
            border: 1px solid var(--border-subtle);
            border-radius: 12px;
            text-decoration: none;
            color: inherit;
            transition: all 0.2s;
            flex: 1;
            max-width: 45%;
        }}

        .ep-nav-btn:hover {{
            border-color: var(--accent-primary);
            background: var(--accent-bg);
        }}

        .ep-nav-prev {{ justify-content: flex-start; }}
        .ep-nav-next {{ justify-content: flex-end; text-align: right; }}

        .ep-nav-btn svg {{ width: 20px; height: 20px; color: var(--text-muted); flex-shrink: 0; }}
        .ep-nav-label {{ font-size: 0.75rem; color: var(--text-muted); text-transform: uppercase; letter-spacing: 0.05em; }}
        .ep-nav-title {{ font-size: 0.9rem; color: var(--text-primary); font-weight: 500; }}
        .ep-nav-disabled {{ visibility: hidden; }}

        .ep-nav-prev .ep-nav-label,
        .ep-nav-prev .ep-nav-title {{ display: block; }}
        .ep-nav-next .ep-nav-label,
        .ep-nav-next .ep-nav-title {{ display: block; }}

        /* Table of Contents */
        .toc {{
            position: fixed;
            top: 50%;
            right: 24px;
            transform: translateY(-50%);
            display: flex;
            flex-direction: column;
            gap: 8px;
            z-index: 100;
        }}

        .toc-link {{
            padding: 8px 12px;
            background: var(--bg-card);
            border: 1px solid var(--border-subtle);
            border-radius: 8px;
            font-size: 0.75rem;
            color: var(--text-muted);
            text-decoration: none;
            transition: all 0.2s;
            backdrop-filter: blur(10px);
        }}

        .toc-link:hover,
        .toc-link.active {{
            border-color: var(--accent-primary);
            color: var(--accent-primary);
            background: var(--accent-bg);
        }}

        /* Clickable stock tags */
        .stock-tag {{
            cursor: pointer;
            text-decoration: none;
        }}

        a.stock-tag:hover {{
            border-color: var(--accent-primary);
            background: var(--accent-bg);
            transform: translateY(-2px);
        }}

        @media (max-width: 1200px) {{
            .toc {{ display: none; }}
        }}

        @media (max-width: 768px) {{
            .episode-nav {{ flex-direction: column; }}
            .ep-nav-btn {{ max-width: 100%; }}
            .ep-nav-next {{ flex-direction: row-reverse; text-align: left; }}
        }}

        @keyframes fadeInUp {{
            from {{
                opacity: 0;
                transform: translateY(20px);
            }}
            to {{
                opacity: 1;
                transform: translateY(0);
            }}
        }}

        .animate-in {{
            animation: fadeInUp 0.6s var(--transition-smooth) forwards;
        }}

        .section {{
            opacity: 0;
            animation: fadeInUp 0.6s var(--transition-smooth) forwards;
        }}

        .section:nth-child(1) {{ animation-delay: 0.1s; }}
        .section:nth-child(2) {{ animation-delay: 0.15s; }}
        .section:nth-child(3) {{ animation-delay: 0.2s; }}
        .section:nth-child(4) {{ animation-delay: 0.25s; }}
        .section:nth-child(5) {{ animation-delay: 0.3s; }}
        .section:nth-child(6) {{ animation-delay: 0.35s; }}

        @media (max-width: 768px) {{
            .container {{
                padding: 0 16px;
            }}

            .episode-header {{
                padding: 24px 0 40px;
            }}

            .share-buttons {{
                flex-wrap: wrap;
            }}

            .stock-grid {{
                gap: 8px;
            }}

            .stock-tag {{
                padding: 10px 14px;
            }}
        }}
    </style>
</head>
<body>
    <div class="progress-bar" id="progressBar"></div>
    <div class="bg-ambient"></div>

    <div class="container">
        <nav class="nav animate-in">
            <a href="/{podcast_id}/" class="nav-back">
                <i data-lucide="arrow-left"></i>
                返回列表
            </a>
            <a href="/" class="nav-logo">
                <div class="nav-logo-icon">
                    <img src="/assets/PodSight-Logo-cropped.jpeg" alt="PodSight">
                </div>
                <span class="nav-logo-text">PodSight 聲見</span>
            </a>
        </nav>

        <header class="episode-header animate-in">
            <div class="episode-meta">
                <span class="episode-badge">
                    <i data-lucide="{config['badge_icon']}"></i>
                    {config['name']}
                </span>
                <span class="episode-date">{date_display}</span>
            </div>
            <h1>{html_escape(episode_info.get('title', display_id))}</h1>
            <p class="episode-subtitle">{html_escape(sections['tldr'][:200]) if sections['tldr'] else config['description']}</p>

            <div class="share-buttons">
                {"" if not episode_info.get("link") else f'''<a href="{episode_info["link"]}" class="share-btn listen-btn" target="_blank" rel="noopener">
                    <i data-lucide="headphones"></i>
                    收聽原節目
                </a>'''}
                <a href="#" class="share-btn" onclick="navigator.share({{title: document.title, url: window.location.href}}); return false;">
                    <i data-lucide="share-2"></i>
                    分享
                </a>
                <a href="https://t.me/share/url?url=${{encodeURIComponent(window.location.href)}}" class="share-btn" target="_blank">
                    <i data-lucide="send"></i>
                    Telegram
                </a>
            </div>
        </header>

        <main class="content">
            {"" if not sections['tldr'] else f'''
            <div class="tldr-box animate-in" id="tldr">
                <div class="tldr-label">一句話總結</div>
                <div class="tldr-text">{html_escape(sections['tldr'])}</div>
            </div>
            '''}

            {"" if not sections['topics'] else f'''
            <section class="section" id="topics">
                <div class="section-header">
                    <div class="section-icon">
                        <i data-lucide="message-square"></i>
                    </div>
                    <h2 class="section-title">主要討論話題</h2>
                </div>
                <div class="topic-list">{topics_html}
                </div>
            </section>
            '''}

            {"" if not sections['strategies'] else f'''
            <section class="section" id="strategies">
                <div class="section-header">
                    <div class="section-icon">
                        <i data-lucide="compass"></i>
                    </div>
                    <h2 class="section-title">操作心法與建議</h2>
                </div>
                <div class="strategy-list">{strategies_html}
                </div>
            </section>
            '''}

            {"" if not sections['stocks'] else f'''
            <section class="section" id="stocks">
                <div class="section-header">
                    <div class="section-icon">
                        <i data-lucide="bar-chart-2"></i>
                    </div>
                    <h2 class="section-title">提到的股票 / ETF</h2>
                </div>
                <div class="stock-grid">{stocks_html}
                </div>
            </section>
            '''}

            {"" if not sections['quotes'] else f'''
            <section class="section" id="quotes">
                <div class="section-header">
                    <div class="section-icon">
                        <i data-lucide="quote"></i>
                    </div>
                    <h2 class="section-title">金句摘錄</h2>
                </div>
                <div class="quote-list">{quotes_html}
                </div>
            </section>
            '''}

            {"" if not sections['humor'] else f'''
            <section class="section" id="humor">
                <div class="section-header">
                    <div class="section-icon">
                        <i data-lucide="smile"></i>
                    </div>
                    <h2 class="section-title">冷笑話 / 幽默金句</h2>
                </div>
                <div class="humor-list">{humor_html}
                </div>
            </section>
            '''}

            {"" if not sections['risks'] else f'''
            <section class="section" id="risks">
                <div class="section-header">
                    <div class="section-icon">
                        <i data-lucide="alert-triangle"></i>
                    </div>
                    <h2 class="section-title">風險提醒</h2>
                </div>
                <div class="risk-list">{risks_html}
                </div>
            </section>
            '''}

            {"" if not sections['conclusion'] else f'''
            <section class="section" id="conclusion">
                <div class="conclusion-box">
                    <div class="conclusion-icon">
                        <i data-lucide="flag"></i>
                    </div>
                    <div class="conclusion-content">
                        <div class="conclusion-label">本集結論</div>
                        <p class="conclusion-text">{html_escape(sections['conclusion'])}</p>
                    </div>
                </div>
            </section>
            '''}
            {nav_html}
        </main>

        <footer class="footer">
            <p class="footer-text">
                摘要由 AI 自動生成，僅供參考 · <a href="/">PodSight</a> · <a href="https://t.me/podsight" target="_blank">Telegram</a>
            </p>
        </footer>
    </div>

    {toc_html}

    <script>
        lucide.createIcons();

        window.addEventListener('scroll', () => {{
            const scrollTop = window.scrollY;
            const docHeight = document.documentElement.scrollHeight - window.innerHeight;
            const progress = (scrollTop / docHeight) * 100;
            document.getElementById('progressBar').style.width = progress + '%';

            // TOC active state
            const sections = document.querySelectorAll('.section[id], .tldr-box[id]');
            const tocLinks = document.querySelectorAll('.toc-link');
            let currentSection = '';

            sections.forEach(section => {{
                const sectionTop = section.offsetTop - 150;
                if (scrollTop >= sectionTop) {{
                    currentSection = section.getAttribute('id');
                }}
            }});

            tocLinks.forEach(link => {{
                link.classList.remove('active');
                if (link.getAttribute('data-section') === currentSection) {{
                    link.classList.add('active');
                }}
            }});
        }});
    </script>
</body>
</html>"""
    return html


def generate_listing_html(podcast_id: str, episodes: list) -> str:
    """Generate HTML for podcast listing page."""
    config = PODCASTS[podcast_id]

    # Build episode list HTML
    episodes_html = ""
    for ep in episodes[:50]:  # Limit to 50 most recent
        ep_id = ep["id"]
        ep_title = ep.get("title", f"{config['episode_prefix']}{ep_id}")
        ep_preview = ep.get("preview", "AI 智慧摘要...")
        ep_date = ep.get("date_str", ep_id if podcast_id == "yutinghao" else "")

        # Format date display
        if podcast_id == "yutinghao":
            date_parts = ep_id.split("-")
            date_display = f"{date_parts[1]}.{date_parts[2]}"
        else:
            date_display = f"{config['episode_prefix']}{ep_id}"

        # Freshness badge
        fresh_label, fresh_class = get_freshness_label(ep_date)
        fresh_badge = f'<span class="fresh-badge {fresh_class}">{fresh_label}</span>' if fresh_label else ""

        # Truncate title nicely - try to cut at a good point
        truncated_title = ep_title[:100] if len(ep_title) <= 100 else ep_title[:97] + "..."

        episodes_html += f"""
            <a href="/{podcast_id}/{ep_id}/" class="episode-card">
                <span class="episode-date-badge">{date_display}{fresh_badge}</span>
                <div class="episode-content">
                    <div class="episode-title">{html_escape(truncated_title)}</div>
                    <div class="episode-preview">{html_escape(ep_preview[:100])}...</div>
                </div>
                <div class="episode-arrow">
                    <i data-lucide="arrow-right"></i>
                </div>
            </a>"""

    html = f"""<!DOCTYPE html>
<html lang="zh-TW">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{config['name']} - PodSight</title>
    <meta name="description" content="{config['name']} AI 智慧摘要">

    <!-- Open Graph -->
    <meta property="og:title" content="{config['name']} - PodSight 聲見">
    <meta property="og:description" content="{config['name']} AI 智慧摘要">
    <meta property="og:image" content="/assets/og-image.png">
    <meta property="og:type" content="website">
    <meta name="twitter:card" content="summary_large_image">

    <!-- Favicon -->
    <link rel="icon" type="image/jpeg" href="/assets/PodSight-Logo-cropped.jpeg">

    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;500;600;700;800&family=Noto+Sans+TC:wght@300;400;500;700&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">

    <script src="https://unpkg.com/lucide@latest/dist/umd/lucide.min.js"></script>

    <style>
        :root {{
            {config['css_vars']}
            --glass-blur: 20px;
            --transition-smooth: cubic-bezier(0.4, 0, 0.2, 1);
        }}

        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        html {{ scroll-behavior: smooth; }}
        body {{
            font-family: 'Noto Sans TC', 'Outfit', sans-serif;
            background: var(--bg-primary);
            color: var(--text-primary);
            min-height: 100vh;
            overflow-x: hidden;
            line-height: 1.6;
        }}

        .bg-ambient {{
            position: fixed;
            top: 0; left: 0;
            width: 100%; height: 100%;
            pointer-events: none;
            z-index: 0;
            background:
                radial-gradient(ellipse at top right, var(--accent-glow) 0%, transparent 50%),
                radial-gradient(ellipse at bottom left, rgba(255,255,255,0.02) 0%, transparent 50%);
        }}

        .container {{
            position: relative;
            z-index: 10;
            max-width: 900px;
            margin: 0 auto;
            padding: 0 24px;
        }}

        .nav {{
            padding: 24px 0;
            display: flex;
            align-items: center;
            justify-content: space-between;
        }}

        .nav-back {{
            display: flex;
            align-items: center;
            gap: 8px;
            color: var(--text-secondary);
            text-decoration: none;
            font-size: 0.9rem;
            transition: color 0.2s;
        }}

        .nav-back:hover {{ color: var(--text-primary); }}
        .nav-back svg {{ width: 18px; height: 18px; }}

        .nav-logo {{
            display: flex;
            align-items: center;
            gap: 8px;
            text-decoration: none;
            color: inherit;
        }}

        .nav-logo-icon {{
            width: 32px; height: 32px;
            border-radius: 8px;
            overflow: hidden;
        }}

        .nav-logo-icon img {{ width: 100%; height: 100%; object-fit: cover; }}
        .nav-logo-text {{ font-family: 'Outfit', sans-serif; font-size: 1.1rem; font-weight: 600; }}

        .podcast-header {{
            text-align: center;
            padding: 60px 0 80px;
            border-bottom: 1px solid var(--border-subtle);
        }}

        .podcast-badge {{
            display: inline-flex;
            align-items: center;
            gap: 8px;
            padding: 8px 16px;
            background: transparent;
            border: 1px solid var(--accent-border);
            border-radius: 100px;
            font-size: 0.85rem;
            color: var(--text-secondary);
            margin-bottom: 24px;
        }}

        .podcast-badge svg {{ width: 16px; height: 16px; }}

        .podcast-header h1 {{
            font-family: 'Outfit', sans-serif;
            font-size: clamp(2.5rem, 6vw, 4rem);
            font-weight: 800;
            margin-bottom: 16px;
            letter-spacing: -0.03em;
            line-height: 1.1;
            background: var(--accent-gradient);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            background-clip: text;
        }}

        .podcast-header .host {{
            font-size: 1.1rem;
            color: var(--text-secondary);
            margin-bottom: 24px;
        }}

        .podcast-header .description {{
            font-size: 1.05rem;
            color: var(--text-muted);
            max-width: 500px;
            margin: 0 auto;
            line-height: 1.8;
        }}

        .controls {{ padding: 32px 0; }}

        .search-box {{
            position: relative;
            max-width: 400px;
        }}

        .search-box svg {{
            position: absolute;
            left: 16px; top: 50%;
            transform: translateY(-50%);
            width: 18px; height: 18px;
            color: var(--text-muted);
        }}

        .search-box input {{
            width: 100%;
            padding: 14px 16px 14px 48px;
            background: transparent;
            border: 1px solid var(--border-subtle);
            border-radius: 8px;
            color: var(--text-primary);
            font-size: 0.95rem;
            font-family: inherit;
            transition: all 0.2s;
        }}

        .search-box input::placeholder {{ color: var(--text-muted); }}
        .search-box input:focus {{ outline: none; border-color: var(--accent-primary); }}

        .episode-count {{
            font-size: 0.85rem;
            color: var(--text-muted);
            margin-bottom: 24px;
            text-transform: uppercase;
            letter-spacing: 0.1em;
        }}

        .episode-list {{
            display: flex;
            flex-direction: column;
            gap: 1px;
            background: var(--border-subtle);
            border-radius: 12px;
            overflow: hidden;
            margin-bottom: 80px;
        }}

        .episode-card {{
            display: flex;
            align-items: center;
            gap: 24px;
            padding: 24px;
            background: var(--bg-secondary);
            text-decoration: none;
            color: inherit;
            transition: all 0.2s var(--transition-smooth);
        }}

        .episode-card:hover {{ background: var(--bg-card-hover); }}

        .episode-date-badge {{
            font-family: 'JetBrains Mono', monospace;
            font-size: 0.8rem;
            font-weight: 500;
            color: var(--text-secondary);
            background: var(--accent-bg);
            padding: 10px 14px;
            border-radius: 6px;
            min-width: 80px;
            text-align: center;
            border: 1px solid var(--border-subtle);
            display: flex;
            flex-direction: column;
            align-items: center;
            gap: 4px;
        }}

        .fresh-badge {{
            font-size: 0.65rem;
            padding: 2px 6px;
            border-radius: 4px;
            font-weight: 600;
            letter-spacing: 0.02em;
        }}

        .fresh-today {{
            background: rgba(34, 197, 94, 0.2);
            color: #22c55e;
        }}

        .fresh-yesterday {{
            background: rgba(59, 130, 246, 0.2);
            color: #3b82f6;
        }}

        .fresh-week {{
            background: rgba(168, 85, 247, 0.15);
            color: #a855f7;
        }}

        .episode-content {{ flex: 1; min-width: 0; }}

        .episode-title {{
            font-weight: 600;
            font-size: 1.05rem;
            margin-bottom: 6px;
            color: var(--text-primary);
        }}

        .episode-preview {{
            font-size: 0.9rem;
            color: var(--text-muted);
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
        }}

        .episode-arrow {{
            width: 36px; height: 36px;
            border-radius: 50%;
            border: 1px solid var(--border-subtle);
            display: flex;
            align-items: center;
            justify-content: center;
            color: var(--text-muted);
            opacity: 0;
            transform: translateX(-8px);
            transition: all 0.2s var(--transition-smooth);
        }}

        .episode-card:hover .episode-arrow {{
            opacity: 1;
            transform: translateX(0);
            color: var(--text-primary);
            border-color: var(--accent-primary);
        }}

        .episode-arrow svg {{ width: 16px; height: 16px; }}

        .footer {{
            padding: 40px 0;
            text-align: center;
            border-top: 1px solid var(--border-subtle);
        }}

        .footer-text {{ font-size: 0.85rem; color: var(--text-muted); }}
        .footer-text a {{ color: var(--text-secondary); text-decoration: none; }}

        @keyframes fadeIn {{
            from {{ opacity: 0; }}
            to {{ opacity: 1; }}
        }}

        .animate-in {{ animation: fadeIn 0.6s var(--transition-smooth) forwards; }}

        .episode-card {{
            animation: fadeIn 0.4s var(--transition-smooth) forwards;
            opacity: 0;
        }}

        .episode-card:nth-child(1) {{ animation-delay: 0.05s; }}
        .episode-card:nth-child(2) {{ animation-delay: 0.1s; }}
        .episode-card:nth-child(3) {{ animation-delay: 0.15s; }}
        .episode-card:nth-child(4) {{ animation-delay: 0.2s; }}
        .episode-card:nth-child(5) {{ animation-delay: 0.25s; }}
        .episode-card:nth-child(n+6) {{ animation-delay: 0.3s; }}

        /* Pagination */
        .pagination {{
            display: flex;
            justify-content: center;
            align-items: center;
            gap: 8px;
            margin: 32px 0;
            flex-wrap: wrap;
        }}

        .pagination button {{
            background: var(--bg-secondary);
            border: 1px solid var(--border-subtle);
            color: var(--text-secondary);
            padding: 10px 16px;
            border-radius: 8px;
            cursor: pointer;
            font-size: 0.9rem;
            transition: all 0.2s var(--transition-smooth);
            display: flex;
            align-items: center;
            gap: 6px;
        }}

        .pagination button:hover:not(:disabled) {{
            background: var(--bg-card-hover);
            border-color: var(--accent-primary);
            color: var(--text-primary);
        }}

        .pagination button:disabled {{
            opacity: 0.4;
            cursor: not-allowed;
        }}

        .pagination button.active {{
            background: var(--accent-primary);
            border-color: var(--accent-primary);
            color: var(--bg-primary);
            font-weight: 600;
        }}

        .pagination button svg {{ width: 16px; height: 16px; }}

        .page-info {{
            color: var(--text-muted);
            font-size: 0.85rem;
            padding: 0 12px;
        }}

        @media (max-width: 768px) {{
            .container {{ padding: 0 16px; }}
            .podcast-header {{ padding: 40px 0 60px; }}
            .episode-card {{
                flex-direction: column;
                align-items: flex-start;
                gap: 12px;
                position: relative;
            }}
            .episode-arrow {{
                opacity: 1;
                transform: translateX(0);
                position: absolute;
                right: 24px; top: 50%;
                transform: translateY(-50%);
            }}
        }}
    </style>
</head>
<body>
    <div class="bg-ambient"></div>

    <div class="container">
        <nav class="nav animate-in">
            <a href="/" class="nav-back">
                <i data-lucide="arrow-left"></i>
                返回首頁
            </a>
            <a href="/" class="nav-logo">
                <div class="nav-logo-icon">
                    <img src="/assets/PodSight-Logo-cropped.jpeg" alt="PodSight">
                </div>
                <span class="nav-logo-text">PodSight 聲見</span>
            </a>
        </nav>

        <header class="podcast-header animate-in">
            <div class="podcast-badge">
                <i data-lucide="{config['badge_icon']}"></i>
                {config['badge_text']}
            </div>
            <h1>{config['name']}</h1>
            <p class="host">主持人：{config['host']}</p>
            <p class="description">{config['description']}</p>
        </header>

        <div class="controls">
            <div class="search-box">
                <i data-lucide="search"></i>
                <input type="text" placeholder="搜尋集數..." id="searchInput">
            </div>
        </div>

        <div class="episode-count">
            共 <strong>{len(episodes)}</strong> 集摘要
        </div>

        <div class="episode-list" id="episodeList">{episodes_html}
        </div>

        <div class="pagination" id="pagination"></div>

        <footer class="footer">
            <p class="footer-text">
                摘要由 AI 自動生成，僅供參考 · <a href="/">PodSight</a> · <a href="https://t.me/podsight" target="_blank">Telegram</a>
            </p>
        </footer>
    </div>

    <script>
        lucide.createIcons();

        const ITEMS_PER_PAGE = 10;
        let currentPage = 1;
        let filteredCards = [];

        const searchInput = document.getElementById('searchInput');
        const episodeCards = Array.from(document.querySelectorAll('.episode-card'));
        const paginationContainer = document.getElementById('pagination');

        function getFilteredCards() {{
            const query = searchInput.value.toLowerCase();
            return episodeCards.filter(card => card.textContent.toLowerCase().includes(query));
        }}

        function renderPagination() {{
            filteredCards = getFilteredCards();
            const totalPages = Math.ceil(filteredCards.length / ITEMS_PER_PAGE);

            if (currentPage > totalPages) currentPage = Math.max(1, totalPages);

            // Hide all cards first
            episodeCards.forEach(card => card.style.display = 'none');

            // Show only current page cards
            const start = (currentPage - 1) * ITEMS_PER_PAGE;
            const end = start + ITEMS_PER_PAGE;
            filteredCards.slice(start, end).forEach((card, i) => {{
                card.style.display = 'flex';
                card.style.animationDelay = `${{i * 0.05}}s`;
            }});

            // Build pagination HTML
            if (totalPages <= 1) {{
                paginationContainer.innerHTML = '';
                return;
            }}

            let html = `
                <button onclick="goToPage(${{currentPage - 1}})" ${{currentPage === 1 ? 'disabled' : ''}}>
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M15 18l-6-6 6-6"/></svg>
                    上一頁
                </button>
            `;

            // Page numbers
            const maxVisible = 5;
            let startPage = Math.max(1, currentPage - Math.floor(maxVisible / 2));
            let endPage = Math.min(totalPages, startPage + maxVisible - 1);
            if (endPage - startPage < maxVisible - 1) startPage = Math.max(1, endPage - maxVisible + 1);

            if (startPage > 1) {{
                html += `<button onclick="goToPage(1)">1</button>`;
                if (startPage > 2) html += `<span class="page-info">...</span>`;
            }}

            for (let i = startPage; i <= endPage; i++) {{
                html += `<button onclick="goToPage(${{i}})" class="${{i === currentPage ? 'active' : ''}}">${{i}}</button>`;
            }}

            if (endPage < totalPages) {{
                if (endPage < totalPages - 1) html += `<span class="page-info">...</span>`;
                html += `<button onclick="goToPage(${{totalPages}})">${{totalPages}}</button>`;
            }}

            html += `
                <button onclick="goToPage(${{currentPage + 1}})" ${{currentPage === totalPages ? 'disabled' : ''}}>
                    下一頁
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M9 18l6-6-6-6"/></svg>
                </button>
            `;

            paginationContainer.innerHTML = html;
        }}

        function goToPage(page) {{
            currentPage = page;
            renderPagination();
            window.scrollTo({{ top: 0, behavior: 'smooth' }});
        }}

        searchInput.addEventListener('input', () => {{
            currentPage = 1;
            renderPagination();
        }});

        // Initial render
        renderPagination();
    </script>
</body>
</html>"""
    return html


def generate_homepage(podcast_counts: dict, latest_episodes: List[dict] = None) -> str:
    """Generate the main homepage."""
    # Build latest episodes HTML
    latest_html = ""
    if latest_episodes:
        for ep in latest_episodes[:6]:
            podcast_id = ep.get("podcast_id", "")
            ep_id = ep.get("id", "")
            ep_title = ep.get("title", "")[:50]
            ep_preview = ep.get("preview", "")[:80]
            podcast_name = PODCASTS.get(podcast_id, {}).get("short_name", podcast_id)
            ep_date = ep.get("date_str", "")

            # Freshness badge
            fresh_label, fresh_class = get_freshness_label(ep_date)
            fresh_badge = f'<span class="fresh-badge {fresh_class}">{fresh_label}</span>' if fresh_label else ""

            latest_html += f'''
                <a href="/{podcast_id}/{ep_id}/" class="latest-card">
                    <div class="latest-meta">
                        <span class="latest-podcast">{podcast_name}</span>
                        {fresh_badge}
                    </div>
                    <div class="latest-title">{html_escape(ep_title)}</div>
                    <div class="latest-preview">{html_escape(ep_preview)}...</div>
                </a>'''

    html = f"""<!DOCTYPE html>
<html lang="zh-TW">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>PodSight 聲見 - AI Podcast Summaries</title>
    <meta name="description" content="台灣財經 Podcast AI 智慧摘要 - 聽見弦外之音，看見核心觀點">

    <!-- Open Graph -->
    <meta property="og:title" content="PodSight 聲見 - AI Podcast Summaries">
    <meta property="og:description" content="台灣財經 Podcast AI 智慧摘要 - 聽見弦外之音，看見核心觀點">
    <meta property="og:image" content="/assets/og-image.png">
    <meta property="og:type" content="website">
    <meta name="twitter:card" content="summary_large_image">

    <!-- Favicon -->
    <link rel="icon" type="image/jpeg" href="/assets/PodSight-Logo-cropped.jpeg">

    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;500;600;700;800&family=Noto+Sans+TC:wght@300;400;500;700&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">

    <script src="https://unpkg.com/lucide@latest/dist/umd/lucide.min.js"></script>

    <style>
        :root {{
            --bg-primary: #050508;
            --bg-secondary: #0a0a0f;
            --bg-card: rgba(255, 255, 255, 0.03);
            --bg-card-hover: rgba(255, 255, 255, 0.06);
            --border-subtle: rgba(255, 255, 255, 0.08);
            --text-primary: #ffffff;
            --text-secondary: rgba(255, 255, 255, 0.7);
            --text-muted: rgba(255, 255, 255, 0.4);

            --gooaye-primary: #4DB8E8;
            --gooaye-gradient: linear-gradient(135deg, #1A6FAF 0%, #4DB8E8 50%, #F5A623 100%);
            --yutinghao-primary: #ffffff;
            --yutinghao-gradient: linear-gradient(135deg, #1A1A1A 0%, #3a3a3a 50%, #ffffff 100%);
            --zhaohua-primary: #F4A97F;
            --zhaohua-gradient: linear-gradient(135deg, #F4A97F 0%, #F5C842 50%, #FFCDB2 100%);

            --transition-smooth: cubic-bezier(0.4, 0, 0.2, 1);
        }}

        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        html {{ scroll-behavior: smooth; }}

        body {{
            font-family: 'Noto Sans TC', 'Outfit', sans-serif;
            background: var(--bg-primary);
            color: var(--text-primary);
            min-height: 100vh;
            overflow-x: hidden;
        }}

        .bg-ambient {{
            position: fixed;
            top: 0; left: 0;
            width: 100%; height: 100%;
            pointer-events: none;
            z-index: 0;
        }}

        .orb {{
            position: absolute;
            border-radius: 50%;
            filter: blur(80px);
            opacity: 0.4;
            animation: float 20s ease-in-out infinite;
        }}

        .orb-1 {{
            width: 600px; height: 600px;
            background: var(--gooaye-gradient);
            top: -200px; right: -200px;
            animation-delay: 0s;
        }}

        .orb-2 {{
            width: 500px; height: 500px;
            background: var(--zhaohua-gradient);
            bottom: -150px; left: -150px;
            animation-delay: -7s;
        }}

        .orb-3 {{
            width: 400px; height: 400px;
            background: linear-gradient(135deg, #ffffff 0%, #808080 100%);
            top: 50%; left: 50%;
            transform: translate(-50%, -50%);
            animation-delay: -14s;
            opacity: 0.2;
        }}

        @keyframes float {{
            0%, 100% {{ transform: translate(0, 0) scale(1); }}
            33% {{ transform: translate(30px, -30px) scale(1.05); }}
            66% {{ transform: translate(-20px, 20px) scale(0.95); }}
        }}

        .container {{
            position: relative;
            z-index: 10;
            max-width: 1200px;
            margin: 0 auto;
            padding: 0 24px;
        }}

        .nav {{
            padding: 32px 0;
            display: flex;
            align-items: center;
            justify-content: space-between;
        }}

        .nav-logo {{
            display: flex;
            align-items: center;
            gap: 12px;
        }}

        .nav-logo-icon {{
            width: 48px; height: 48px;
            border-radius: 14px;
            overflow: hidden;
            box-shadow: 0 8px 32px rgba(77, 184, 232, 0.3);
        }}

        .nav-logo-icon img {{
            width: 100%; height: 100%;
            object-fit: cover;
        }}

        .nav-logo-text {{
            font-family: 'Outfit', sans-serif;
            font-size: 1.5rem;
            font-weight: 700;
            letter-spacing: -0.02em;
        }}

        .hero {{
            text-align: center;
            padding: 100px 0 120px;
        }}

        .hero-badge {{
            display: inline-flex;
            align-items: center;
            gap: 8px;
            padding: 8px 20px;
            background: var(--bg-card);
            border: 1px solid var(--border-subtle);
            border-radius: 100px;
            font-size: 0.85rem;
            color: var(--text-secondary);
            margin-bottom: 32px;
            backdrop-filter: blur(10px);
        }}

        .hero-badge svg {{ width: 16px; height: 16px; }}

        .hero h1 {{
            font-family: 'Outfit', sans-serif;
            font-size: clamp(3rem, 8vw, 5.5rem);
            font-weight: 800;
            line-height: 1.05;
            letter-spacing: -0.04em;
            margin-bottom: 24px;
        }}

        .hero h1 .gradient {{
            background: linear-gradient(135deg, var(--gooaye-primary), var(--zhaohua-primary), var(--yutinghao-primary));
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            background-clip: text;
        }}

        .hero-subtitle {{
            font-size: 1.25rem;
            color: var(--text-secondary);
            max-width: 600px;
            margin: 0 auto;
            line-height: 1.8;
        }}

        .podcasts-section {{
            padding: 40px 0 120px;
        }}

        .section-label {{
            font-size: 0.8rem;
            font-weight: 600;
            text-transform: uppercase;
            letter-spacing: 0.15em;
            color: var(--text-muted);
            margin-bottom: 32px;
        }}

        .podcast-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(340px, 1fr));
            gap: 24px;
        }}

        .podcast-card {{
            position: relative;
            background: var(--bg-card);
            border: 1px solid var(--border-subtle);
            border-radius: 24px;
            padding: 40px 32px;
            text-decoration: none;
            color: inherit;
            transition: all 0.4s var(--transition-smooth);
            overflow: hidden;
        }}

        .podcast-card::before {{
            content: '';
            position: absolute;
            top: 0; left: 0;
            width: 100%; height: 100%;
            opacity: 0;
            transition: opacity 0.4s;
        }}

        .podcast-card.gooaye::before {{ background: linear-gradient(135deg, rgba(77,184,232,0.1), rgba(245,166,35,0.05)); }}
        .podcast-card.yutinghao::before {{ background: linear-gradient(135deg, rgba(255,255,255,0.05), rgba(128,128,128,0.03)); }}
        .podcast-card.zhaohua::before {{ background: linear-gradient(135deg, rgba(244,169,127,0.1), rgba(245,200,66,0.05)); }}

        .podcast-card:hover {{
            transform: translateY(-8px);
            border-color: transparent;
            box-shadow: 0 20px 60px rgba(0,0,0,0.4);
        }}

        .podcast-card:hover::before {{ opacity: 1; }}

        .podcast-card-content {{ position: relative; z-index: 1; }}

        .podcast-icon {{
            width: 64px; height: 64px;
            border-radius: 16px;
            display: flex;
            align-items: center;
            justify-content: center;
            margin-bottom: 24px;
        }}

        .podcast-card.gooaye .podcast-icon {{ background: var(--gooaye-gradient); }}
        .podcast-card.yutinghao .podcast-icon {{ background: var(--yutinghao-gradient); }}
        .podcast-card.zhaohua .podcast-icon {{ background: var(--zhaohua-gradient); }}

        .podcast-icon svg {{
            width: 32px; height: 32px;
            color: var(--bg-primary);
        }}

        .podcast-card h3 {{
            font-family: 'Outfit', sans-serif;
            font-size: 1.75rem;
            font-weight: 700;
            margin-bottom: 8px;
            letter-spacing: -0.02em;
        }}

        .podcast-card .host {{
            font-size: 0.95rem;
            color: var(--text-secondary);
            margin-bottom: 16px;
        }}

        .podcast-card .description {{
            font-size: 0.95rem;
            color: var(--text-muted);
            line-height: 1.7;
            margin-bottom: 24px;
        }}

        .podcast-card .stats {{
            display: flex;
            align-items: center;
            gap: 16px;
        }}

        .stat {{
            display: flex;
            align-items: center;
            gap: 6px;
            font-size: 0.85rem;
            color: var(--text-secondary);
        }}

        .stat svg {{ width: 16px; height: 16px; }}

        .podcast-card .arrow {{
            position: absolute;
            bottom: 32px; right: 32px;
            width: 48px; height: 48px;
            border-radius: 50%;
            border: 1px solid var(--border-subtle);
            display: flex;
            align-items: center;
            justify-content: center;
            color: var(--text-muted);
            opacity: 0;
            transform: translateX(-12px);
            transition: all 0.3s var(--transition-smooth);
        }}

        .podcast-card:hover .arrow {{
            opacity: 1;
            transform: translateX(0);
        }}

        .podcast-card.gooaye:hover .arrow {{ border-color: var(--gooaye-primary); color: var(--gooaye-primary); }}
        .podcast-card.yutinghao:hover .arrow {{ border-color: var(--yutinghao-primary); color: var(--yutinghao-primary); }}
        .podcast-card.zhaohua:hover .arrow {{ border-color: var(--zhaohua-primary); color: var(--zhaohua-primary); }}

        .arrow svg {{ width: 20px; height: 20px; }}

        .footer {{
            padding: 48px 0;
            border-top: 1px solid var(--border-subtle);
            text-align: center;
        }}

        .footer-text {{
            font-size: 0.9rem;
            color: var(--text-muted);
        }}

        @keyframes fadeInUp {{
            from {{ opacity: 0; transform: translateY(30px); }}
            to {{ opacity: 1; transform: translateY(0); }}
        }}

        .animate-in {{
            animation: fadeInUp 0.8s var(--transition-smooth) forwards;
            opacity: 0;
        }}

        .delay-1 {{ animation-delay: 0.1s; }}
        .delay-2 {{ animation-delay: 0.2s; }}
        .delay-3 {{ animation-delay: 0.3s; }}
        .delay-4 {{ animation-delay: 0.4s; }}

        /* Latest Episodes Section */
        .latest-section {{
            padding: 0 0 80px;
        }}

        .latest-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
            gap: 16px;
        }}

        .latest-card {{
            background: var(--bg-card);
            border: 1px solid var(--border-subtle);
            border-radius: 16px;
            padding: 24px;
            text-decoration: none;
            color: inherit;
            transition: all 0.3s var(--transition-smooth);
        }}

        .latest-card:hover {{
            transform: translateY(-4px);
            border-color: rgba(255,255,255,0.15);
            background: var(--bg-card-hover);
        }}

        .latest-meta {{
            display: flex;
            align-items: center;
            gap: 10px;
            margin-bottom: 12px;
        }}

        .latest-podcast {{
            font-size: 0.75rem;
            font-weight: 600;
            text-transform: uppercase;
            letter-spacing: 0.05em;
            color: var(--text-muted);
        }}

        .latest-title {{
            font-weight: 600;
            font-size: 1rem;
            margin-bottom: 8px;
            color: var(--text-primary);
            line-height: 1.4;
        }}

        .latest-preview {{
            font-size: 0.85rem;
            color: var(--text-muted);
            line-height: 1.6;
        }}

        /* Freshness badges */
        .fresh-badge {{
            font-size: 0.65rem;
            padding: 3px 8px;
            border-radius: 4px;
            font-weight: 600;
            letter-spacing: 0.02em;
        }}

        .fresh-today {{
            background: rgba(34, 197, 94, 0.2);
            color: #22c55e;
        }}

        .fresh-yesterday {{
            background: rgba(59, 130, 246, 0.2);
            color: #3b82f6;
        }}

        .fresh-week {{
            background: rgba(168, 85, 247, 0.15);
            color: #a855f7;
        }}

        /* Telegram CTA */
        .telegram-cta {{
            display: inline-flex;
            align-items: center;
            gap: 8px;
            padding: 12px 24px;
            background: rgba(0, 136, 204, 0.15);
            border: 1px solid rgba(0, 136, 204, 0.3);
            border-radius: 100px;
            color: #0088cc;
            text-decoration: none;
            font-size: 0.9rem;
            font-weight: 500;
            transition: all 0.2s;
            margin-top: 32px;
        }}

        .telegram-cta:hover {{
            background: rgba(0, 136, 204, 0.25);
            transform: translateY(-2px);
        }}

        .telegram-cta svg {{ width: 18px; height: 18px; }}

        @media (max-width: 768px) {{
            .container {{ padding: 0 16px; }}
            .hero {{ padding: 60px 0 80px; }}
            .podcast-grid {{ grid-template-columns: 1fr; }}
            .latest-grid {{ grid-template-columns: 1fr; }}
            .orb {{ opacity: 0.25; }}
        }}
    </style>
</head>
<body>
    <div class="bg-ambient">
        <div class="orb orb-1"></div>
        <div class="orb orb-2"></div>
        <div class="orb orb-3"></div>
    </div>

    <div class="container">
        <nav class="nav animate-in">
            <div class="nav-logo">
                <div class="nav-logo-icon">
                    <img src="/assets/PodSight-Logo-cropped.jpeg" alt="PodSight">
                </div>
                <span class="nav-logo-text">PodSight 聲見</span>
            </div>
        </nav>

        <section class="hero">
            <div class="hero-badge animate-in delay-1">
                <i data-lucide="sparkles"></i>
                AI-Powered Summaries
            </div>
            <h1 class="animate-in delay-2">
                聽不完？<br><span class="gradient">讓 AI 幫你抓重點</span>
            </h1>
            <p class="hero-subtitle animate-in delay-3">
                台灣財經 Podcast 智慧摘要，快速掌握每集精華內容、投資觀點與市場分析。
            </p>
        </section>

        {"" if not latest_html else f'''
        <section class="latest-section">
            <div class="section-label animate-in delay-2">最新摘要</div>
            <div class="latest-grid animate-in delay-3">{latest_html}
            </div>
        </section>
        '''}

        <section class="podcasts-section">
            <div class="section-label animate-in delay-3">收錄節目</div>

            <div class="podcast-grid">
                <a href="/gooaye/" class="podcast-card gooaye animate-in delay-3">
                    <div class="podcast-card-content">
                        <div class="podcast-icon">
                            <i data-lucide="trending-up"></i>
                        </div>
                        <h3>股癌</h3>
                        <p class="host">謝孟恭 Melody Hsieh</p>
                        <p class="description">用輕鬆詼諧的方式，分享投資心法與市場觀察。</p>
                        <div class="stats">
                            <span class="stat">
                                <i data-lucide="file-text"></i>
                                {podcast_counts.get('gooaye', 0)} 集摘要
                            </span>
                        </div>
                    </div>
                    <div class="arrow">
                        <i data-lucide="arrow-right"></i>
                    </div>
                </a>

                <a href="/yutinghao/" class="podcast-card yutinghao animate-in delay-3">
                    <div class="podcast-card-content">
                        <div class="podcast-icon">
                            <i data-lucide="bar-chart-2"></i>
                        </div>
                        <h3>游庭皓的財經皓角</h3>
                        <p class="host">游庭皓</p>
                        <p class="description">深入淺出的財經分析，帶你看懂市場邏輯。</p>
                        <div class="stats">
                            <span class="stat">
                                <i data-lucide="file-text"></i>
                                {podcast_counts.get('yutinghao', 0)} 集摘要
                            </span>
                        </div>
                    </div>
                    <div class="arrow">
                        <i data-lucide="arrow-right"></i>
                    </div>
                </a>

                <a href="/zhaohua/" class="podcast-card zhaohua animate-in delay-4">
                    <div class="podcast-card-content">
                        <div class="podcast-icon">
                            <i data-lucide="mic"></i>
                        </div>
                        <h3>兆華與股惑仔</h3>
                        <p class="host">李兆華</p>
                        <p class="description">專業與生活化角度，掌握台股脈動。</p>
                        <div class="stats">
                            <span class="stat">
                                <i data-lucide="file-text"></i>
                                {podcast_counts.get('zhaohua', 0)} 集摘要
                            </span>
                        </div>
                    </div>
                    <div class="arrow">
                        <i data-lucide="arrow-right"></i>
                    </div>
                </a>
            </div>
        </section>

        <footer class="footer">
            <a href="https://t.me/podsight" target="_blank" class="telegram-cta">
                <i data-lucide="send"></i>
                訂閱 Telegram 頻道
            </a>
            <p class="footer-text" style="margin-top: 24px;">
                摘要由 AI 自動生成，僅供參考 · PodSight
            </p>
        </footer>
    </div>

    <script>
        lucide.createIcons();
    </script>
</body>
</html>"""
    return html


def generate_stock_search_page(stock_index: Dict[str, List[dict]]) -> str:
    """Generate the stock search page."""
    # Sort stocks alphabetically
    sorted_stocks = sorted(stock_index.keys())

    # Build stock list HTML
    stocks_html = ""
    for stock_name in sorted_stocks:
        episodes = stock_index[stock_name]
        ep_count = len(episodes)
        # Get unique podcasts
        podcasts = list(set([ep["podcast_id"] for ep in episodes]))
        podcast_badges = " ".join([f'<span class="stock-podcast-badge">{PODCASTS.get(p, {}).get("short_name", p)}</span>' for p in podcasts[:3]])

        stocks_html += f'''
            <div class="stock-index-item" data-stock="{html_escape(stock_name.lower())}">
                <div class="stock-index-name">{html_escape(stock_name)}</div>
                <div class="stock-index-meta">
                    {podcast_badges}
                    <span class="stock-index-count">{ep_count} 集提及</span>
                </div>
                <div class="stock-index-episodes">'''

        for ep in episodes[:5]:
            podcast_id = ep["podcast_id"]
            ep_id = ep["id"]
            ep_title = ep.get("title", "")[:40]
            stocks_html += f'''
                    <a href="/{podcast_id}/{ep_id}/" class="stock-episode-link">{html_escape(ep_title)}</a>'''

        if ep_count > 5:
            stocks_html += f'<span class="stock-more">+{ep_count - 5} 更多</span>'

        stocks_html += '''
                </div>
            </div>'''

    html = f'''<!DOCTYPE html>
<html lang="zh-TW">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>股票搜尋 - PodSight</title>
    <meta name="description" content="搜尋 Podcast 中提到的股票">

    <link rel="icon" type="image/jpeg" href="/assets/PodSight-Logo-cropped.jpeg">
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;500;600;700;800&family=Noto+Sans+TC:wght@300;400;500;700&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
    <script src="https://unpkg.com/lucide@latest/dist/umd/lucide.min.js"></script>

    <style>
        :root {{
            --bg-primary: #050508;
            --bg-secondary: #0a0a0f;
            --bg-card: rgba(255, 255, 255, 0.03);
            --bg-card-hover: rgba(255, 255, 255, 0.06);
            --border-subtle: rgba(255, 255, 255, 0.08);
            --text-primary: #ffffff;
            --text-secondary: rgba(255, 255, 255, 0.7);
            --text-muted: rgba(255, 255, 255, 0.4);
            --accent-primary: #4DB8E8;
            --accent-bg: rgba(77, 184, 232, 0.12);
            --transition-smooth: cubic-bezier(0.4, 0, 0.2, 1);
        }}

        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            font-family: 'Noto Sans TC', 'Outfit', sans-serif;
            background: var(--bg-primary);
            color: var(--text-primary);
            min-height: 100vh;
            line-height: 1.6;
        }}

        .container {{
            max-width: 900px;
            margin: 0 auto;
            padding: 0 24px;
        }}

        .nav {{
            padding: 24px 0;
            display: flex;
            align-items: center;
            justify-content: space-between;
        }}

        .nav-back {{
            display: flex;
            align-items: center;
            gap: 8px;
            color: var(--text-secondary);
            text-decoration: none;
            font-size: 0.9rem;
            transition: color 0.2s;
        }}

        .nav-back:hover {{ color: var(--text-primary); }}
        .nav-back svg {{ width: 18px; height: 18px; }}

        .nav-logo {{
            display: flex;
            align-items: center;
            gap: 8px;
            text-decoration: none;
            color: inherit;
        }}

        .nav-logo-icon {{
            width: 32px; height: 32px;
            border-radius: 8px;
            overflow: hidden;
        }}

        .nav-logo-icon img {{ width: 100%; height: 100%; object-fit: cover; }}
        .nav-logo-text {{ font-family: 'Outfit', sans-serif; font-size: 1.1rem; font-weight: 600; }}

        .page-header {{
            text-align: center;
            padding: 60px 0;
        }}

        .page-header h1 {{
            font-family: 'Outfit', sans-serif;
            font-size: 2.5rem;
            font-weight: 700;
            margin-bottom: 16px;
            background: linear-gradient(135deg, var(--accent-primary), #ffffff);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
        }}

        .page-header p {{
            color: var(--text-muted);
            font-size: 1.05rem;
        }}

        .search-box {{
            position: relative;
            max-width: 500px;
            margin: 0 auto 48px;
        }}

        .search-box svg {{
            position: absolute;
            left: 20px; top: 50%;
            transform: translateY(-50%);
            width: 20px; height: 20px;
            color: var(--text-muted);
        }}

        .search-box input {{
            width: 100%;
            padding: 18px 24px 18px 56px;
            background: var(--bg-card);
            border: 1px solid var(--border-subtle);
            border-radius: 12px;
            color: var(--text-primary);
            font-size: 1rem;
            font-family: inherit;
            transition: all 0.2s;
        }}

        .search-box input::placeholder {{ color: var(--text-muted); }}
        .search-box input:focus {{ outline: none; border-color: var(--accent-primary); }}

        .stock-count {{
            text-align: center;
            font-size: 0.85rem;
            color: var(--text-muted);
            margin-bottom: 32px;
        }}

        .stock-index {{
            display: flex;
            flex-direction: column;
            gap: 12px;
        }}

        .stock-index-item {{
            background: var(--bg-card);
            border: 1px solid var(--border-subtle);
            border-radius: 12px;
            padding: 20px;
            transition: all 0.2s;
        }}

        .stock-index-item:hover {{
            border-color: var(--accent-primary);
            background: var(--bg-card-hover);
        }}

        .stock-index-item.hidden {{ display: none; }}

        .stock-index-name {{
            font-weight: 600;
            font-size: 1.1rem;
            color: var(--accent-primary);
            margin-bottom: 8px;
        }}

        .stock-index-meta {{
            display: flex;
            align-items: center;
            gap: 8px;
            margin-bottom: 12px;
            flex-wrap: wrap;
        }}

        .stock-podcast-badge {{
            font-size: 0.7rem;
            padding: 3px 8px;
            background: var(--accent-bg);
            border-radius: 4px;
            color: var(--text-secondary);
        }}

        .stock-index-count {{
            font-size: 0.8rem;
            color: var(--text-muted);
        }}

        .stock-index-episodes {{
            display: flex;
            flex-wrap: wrap;
            gap: 8px;
        }}

        .stock-episode-link {{
            font-size: 0.85rem;
            color: var(--text-secondary);
            text-decoration: none;
            padding: 6px 12px;
            background: var(--bg-secondary);
            border-radius: 6px;
            transition: all 0.2s;
        }}

        .stock-episode-link:hover {{
            color: var(--accent-primary);
            background: var(--accent-bg);
        }}

        .stock-more {{
            font-size: 0.8rem;
            color: var(--text-muted);
            padding: 6px 12px;
        }}

        .no-results {{
            text-align: center;
            padding: 60px 0;
            color: var(--text-muted);
            display: none;
        }}

        .footer {{
            padding: 48px 0;
            border-top: 1px solid var(--border-subtle);
            text-align: center;
            margin-top: 60px;
        }}

        .footer-text {{ font-size: 0.85rem; color: var(--text-muted); }}
        .footer-text a {{ color: var(--text-secondary); text-decoration: none; }}

        @media (max-width: 768px) {{
            .container {{ padding: 0 16px; }}
            .page-header {{ padding: 40px 0; }}
            .page-header h1 {{ font-size: 2rem; }}
        }}
    </style>
</head>
<body>
    <div class="container">
        <nav class="nav">
            <a href="/" class="nav-back">
                <i data-lucide="arrow-left"></i>
                返回首頁
            </a>
            <a href="/" class="nav-logo">
                <div class="nav-logo-icon">
                    <img src="/assets/PodSight-Logo-cropped.jpeg" alt="PodSight">
                </div>
                <span class="nav-logo-text">PodSight 聲見</span>
            </a>
        </nav>

        <header class="page-header">
            <h1>股票搜尋</h1>
            <p>搜尋 Podcast 中提到的股票與 ETF</p>
        </header>

        <div class="search-box">
            <i data-lucide="search"></i>
            <input type="text" placeholder="搜尋股票名稱或代號..." id="stockSearch">
        </div>

        <div class="stock-count">
            共 <strong>{len(stock_index)}</strong> 檔股票 / ETF
        </div>

        <div class="stock-index" id="stockIndex">{stocks_html}
        </div>

        <div class="no-results" id="noResults">
            找不到符合的股票
        </div>

        <footer class="footer">
            <p class="footer-text">
                摘要由 AI 自動生成，僅供參考 · <a href="/">PodSight</a> · <a href="https://t.me/podsight" target="_blank">Telegram</a>
            </p>
        </footer>
    </div>

    <script>
        lucide.createIcons();

        const searchInput = document.getElementById('stockSearch');
        const stockItems = document.querySelectorAll('.stock-index-item');
        const noResults = document.getElementById('noResults');

        // Check URL params for initial search
        const urlParams = new URLSearchParams(window.location.search);
        const initialQuery = urlParams.get('q');
        if (initialQuery) {{
            searchInput.value = initialQuery;
            filterStocks(initialQuery);
        }}

        searchInput.addEventListener('input', (e) => {{
            filterStocks(e.target.value);
        }});

        function filterStocks(query) {{
            query = query.toLowerCase().trim();
            let visibleCount = 0;

            stockItems.forEach(item => {{
                const stockName = item.getAttribute('data-stock');
                if (!query || stockName.includes(query)) {{
                    item.classList.remove('hidden');
                    visibleCount++;
                }} else {{
                    item.classList.add('hidden');
                }}
            }});

            noResults.style.display = visibleCount === 0 ? 'block' : 'none';
        }}
    </script>
</body>
</html>'''
    return html


def html_escape(text: str) -> str:
    """Escape HTML special characters."""
    if not text:
        return ""
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&#39;")
    )


def load_episodes_data(podcast_id: str) -> dict:
    """Load episodes.json and return a dict mapping episode_number to episode data.
    Also maps by title for podcasts without episode numbers (yutinghao)."""
    episodes_file = DATA_DIR / podcast_id / "episodes.json"
    if not episodes_file.exists():
        return {}

    try:
        with open(episodes_file, "r", encoding="utf-8") as f:
            episodes = json.load(f)
        result = {}
        for ep in episodes:
            if ep.get("episode_number"):
                result[ep["episode_number"]] = ep
            # Also map by title for date-based lookups
            if ep.get("title"):
                result[ep["title"]] = ep
        return result
    except Exception:
        return {}


def main():
    """Generate the complete public site."""
    print("Generating PodSight public site...")

    # Track counts and collect data
    podcast_counts = {}
    total_episodes = 0
    all_episodes = []  # For "latest" feed
    stock_index = {}  # For stock search

    # First pass: collect all episode data
    all_podcast_episodes = {}

    for podcast_id, config in PODCASTS.items():
        print(f"\nProcessing {config['name']}...")

        summaries_dir = DATA_DIR / podcast_id / "summaries"
        if not summaries_dir.exists():
            print(f"  No summaries directory found")
            continue

        # Load episodes data for original titles
        episodes_data = load_episodes_data(podcast_id)

        # Get all summary files
        summary_files = list(summaries_dir.glob("*_summary.txt"))
        print(f"  Found {len(summary_files)} summaries")

        episodes = []
        episodes_with_sections = []  # Store sections for second pass

        # Sort by proper key (date for yutinghao, episode number for others)
        sorted_files = sorted(
            summary_files,
            key=lambda f: get_sort_key(f.name, podcast_id),
            reverse=True
        )
        for summary_file in sorted_files:
            episode_id = get_episode_id(summary_file.name, podcast_id)
            if not episode_id:
                continue

            # Read and parse summary
            try:
                content = summary_file.read_text(encoding="utf-8")
                sections = parse_summary(content)
            except Exception as e:
                print(f"  Error parsing {summary_file.name}: {e}")
                continue

            # Get original episode title from episodes.json
            title = None
            pub_date = None
            episode_link = ""
            if podcast_id in ["gooaye", "zhaohua"]:
                # Numbered episodes - look up by episode number
                ep_num = int(episode_id) if episode_id.isdigit() else None
                if ep_num and ep_num in episodes_data:
                    title = episodes_data[ep_num].get("title", "")
                    episode_link = episodes_data[ep_num].get("link", "")
                    # Parse RFC 2822 date format to YYYY-MM-DD
                    raw_date = episodes_data[ep_num].get("published", "")
                    pub_date = parse_rfc_date(raw_date) or ""
            else:
                # Date-based (yutinghao) - use filename title
                title = get_episode_title(summary_file.name, podcast_id)
                pub_date = episode_id  # Episode ID is the date
                # Look up link by date prefix in RSS titles (e.g. "2026-01-06" -> "2026/1/6")
                if episode_id:
                    parts = episode_id.split("-")  # "2026-01-06" -> ["2026","01","06"]
                    if len(parts) == 3:
                        date_prefix = f"{parts[0]}/{int(parts[1])}/{int(parts[2])}"
                        for key, ep_data in episodes_data.items():
                            if isinstance(key, str) and key.startswith(date_prefix):
                                episode_link = ep_data.get("link", "")
                                break

            # Fallback to TLDR if no title found
            if not title and sections["tldr"]:
                title = sections["tldr"][:50]

            # Get date string for freshness
            date_str = extract_episode_date(episode_id, podcast_id, summary_file.name) or pub_date or ""

            # Create episode info
            episode_info = {
                "id": episode_id,
                "title": title or f"{config['episode_prefix']}{episode_id}",
                "preview": sections["tldr"][:100] if sections["tldr"] else "",
                "date": episode_id if podcast_id == "yutinghao" else "",
                "date_str": date_str,
                "podcast_id": podcast_id,
                "link": episode_link,
            }
            episodes.append(episode_info)
            episodes_with_sections.append((episode_info, sections, summary_file.name))

            # Add to all_episodes for "latest" feed
            all_episodes.append(episode_info)

            # Build stock index
            for stock in sections.get("stocks", []):
                stock_name = stock.get("symbol", "").split("(")[0].strip()
                if stock_name:
                    if stock_name not in stock_index:
                        stock_index[stock_name] = []
                    stock_index[stock_name].append({
                        "podcast_id": podcast_id,
                        "id": episode_id,
                        "title": title or episode_id,
                    })

        all_podcast_episodes[podcast_id] = episodes_with_sections
        podcast_counts[podcast_id] = len(episodes)
        total_episodes += len(episodes)

    # Build balanced "latest" feed - interleaved for grid: 股癌, YTH, 兆華, 股癌, YTH, 兆華
    latest_by_podcast = {}
    for podcast_id in ["gooaye", "yutinghao", "zhaohua"]:
        latest_by_podcast[podcast_id] = [ep for ep in all_episodes if ep.get("podcast_id") == podcast_id][:2]

    # Interleave: position 0,3 = gooaye, 1,4 = yth, 2,5 = zhaohua
    latest_balanced = [
        latest_by_podcast["gooaye"][0] if latest_by_podcast["gooaye"] else None,
        latest_by_podcast["yutinghao"][0] if latest_by_podcast["yutinghao"] else None,
        latest_by_podcast["zhaohua"][0] if latest_by_podcast["zhaohua"] else None,
        latest_by_podcast["gooaye"][1] if len(latest_by_podcast["gooaye"]) > 1 else None,
        latest_by_podcast["yutinghao"][1] if len(latest_by_podcast["yutinghao"]) > 1 else None,
        latest_by_podcast["zhaohua"][1] if len(latest_by_podcast["zhaohua"]) > 1 else None,
    ]
    latest_balanced = [ep for ep in latest_balanced if ep]  # Remove None entries

    # Second pass: generate episode pages with prev/next navigation
    for podcast_id, episodes_with_sections in all_podcast_episodes.items():
        config = PODCASTS[podcast_id]
        episodes = [e[0] for e in episodes_with_sections]

        for i, (episode_info, sections, filename) in enumerate(episodes_with_sections):
            episode_id = episode_info["id"]

            # Determine prev/next episodes (prev = newer, next = older in our sorted list)
            prev_episode = episodes[i - 1] if i > 0 else None
            next_episode = episodes[i + 1] if i < len(episodes) - 1 else None

            # Generate episode page with navigation
            episode_html = generate_episode_html(
                podcast_id, episode_id, sections, episode_info,
                prev_episode=prev_episode, next_episode=next_episode
            )

            # Write episode page
            episode_dir = OUTPUT_DIR / podcast_id / episode_id
            episode_dir.mkdir(parents=True, exist_ok=True)
            (episode_dir / "index.html").write_text(episode_html, encoding="utf-8")

        # Generate listing page
        if episodes:
            listing_html = generate_listing_html(podcast_id, episodes)
            listing_dir = OUTPUT_DIR / podcast_id
            listing_dir.mkdir(parents=True, exist_ok=True)
            (listing_dir / "index.html").write_text(listing_html, encoding="utf-8")

        print(f"  Generated {len(episodes)} episode pages")

    # Generate stock search page
    if stock_index:
        print(f"\nGenerating stock search page ({len(stock_index)} stocks)...")
        stock_html = generate_stock_search_page(stock_index)
        stock_dir = OUTPUT_DIR / "stocks"
        stock_dir.mkdir(parents=True, exist_ok=True)
        (stock_dir / "index.html").write_text(stock_html, encoding="utf-8")

    # Generate homepage with latest episodes (balanced: 2 from each podcast)
    homepage_html = generate_homepage(podcast_counts, latest_episodes=latest_balanced[:6])
    (OUTPUT_DIR / "index.html").write_text(homepage_html, encoding="utf-8")
    print(f"\nGenerated homepage")

    print(f"\n{'='*50}")
    print(f"Total: {total_episodes} episode pages generated")
    print(f"Output: {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
