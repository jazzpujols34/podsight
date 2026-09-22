#!/usr/bin/env python3
"""
Search tool for Gooaye transcripts.

Usage:
    python search.py "台積電"                    # Search all transcripts
    python search.py "台積電" --ep 620-630       # Search specific episode range
    python search.py "台積電" --summary          # Search summaries only
    python search.py "台積電" --limit 50         # Show up to 50 results
    python search.py "台積電" --json             # Output as JSON

Output shows:
- Episode number
- Timestamp [MM:SS]
- Matching line with search term highlighted
"""

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Generator

# Add project root to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.config import get_podcast_config, get_episode_number_from_filename, parse_episode_range

# Default to gooaye podcast for backwards compatibility
_default = get_podcast_config()
TRANSCRIPT_DIR = _default.transcript_dir
SUMMARY_DIR = _default.summary_dir
INDEX_DIR = _default.data_dir / "index"

# ANSI colors for terminal output
HIGHLIGHT_START = "\033[1;33m"  # Bold yellow
HIGHLIGHT_END = "\033[0m"       # Reset


@dataclass
class SearchResult:
    episode_number: int
    timestamp: str
    line_number: int
    text: str
    matched_text: str
    source: str  # "transcript" or "summary"
    company: str | None = None  # from the Jev index, if one exists for this episode
    topic: str | None = None


def parse_timestamp(line: str) -> str:
    """Extract timestamp from line like '[07:25] text...'"""
    match = re.match(r'\[(\d+:\d+)\]', line)
    return match.group(1) if match else ""


def _timestamp_to_seconds(timestamp: str) -> int | None:
    """'MM:SS' -> total seconds, or None if not parseable."""
    parts = timestamp.split(":")
    if len(parts) != 2:
        return None
    try:
        minutes, seconds = int(parts[0]), int(parts[1])
    except ValueError:
        return None
    return minutes * 60 + seconds


def load_index(episode_id: str) -> dict | None:
    """Read data/{podcast}/index/{episode_id}.json, or None if missing/unreadable."""
    index_path = INDEX_DIR / f"{episode_id}.json"
    if not index_path.exists():
        return None
    try:
        return json.loads(index_path.read_text(encoding="utf-8"))
    except Exception:
        return None


def find_window(index_data: dict, seconds: int) -> dict | None:
    """The window whose [start, end) contains `seconds`, or None."""
    for window in index_data.get("windows", []):
        if window["start"] <= seconds < window["end"]:
            return window
    return None


def search_file(
    file_path: Path,
    query: str,
    source: str,
    case_sensitive: bool = False,
    index_cache: dict | None = None,
    company_filter: str | None = None,
    topic_filter: str | None = None,
) -> Generator[SearchResult, None, None]:
    """Search a single file for the query string."""
    ep_num = get_episode_number_from_filename(file_path.name)
    if ep_num is None:
        return

    try:
        content = file_path.read_text(encoding='utf-8')
    except Exception:
        return

    flags = 0 if case_sensitive else re.IGNORECASE
    pattern = re.compile(re.escape(query), flags)
    episode_id = f"EP{ep_num:04d}"

    for line_num, line in enumerate(content.split('\n'), 1):
        if pattern.search(line):
            timestamp = parse_timestamp(line) if source == "transcript" else ""

            # Find the actual matched text for highlighting
            match = pattern.search(line)
            matched_text = match.group(0) if match else query

            company, topic = None, None
            if source == "transcript" and timestamp:
                if index_cache is not None:
                    if episode_id not in index_cache:
                        index_cache[episode_id] = load_index(episode_id)
                    index_data = index_cache[episode_id]
                else:
                    index_data = load_index(episode_id)
                if index_data:
                    seconds = _timestamp_to_seconds(timestamp)
                    if seconds is not None:
                        window = find_window(index_data, seconds)
                        if window:
                            company = window.get("company")
                            topic = window.get("topic")

            if company_filter is not None and (company or "").lower() != company_filter.lower():
                continue
            if topic_filter is not None and topic_filter.lower() not in (topic or "").lower():
                continue

            yield SearchResult(
                episode_number=ep_num,
                timestamp=timestamp,
                line_number=line_num,
                text=line.strip(),
                matched_text=matched_text,
                source=source,
                company=company,
                topic=topic,
            )


def search_transcripts(
    query: str,
    ep_start: int | None = None,
    ep_end: int | None = None,
    search_summaries: bool = False,
    limit: int = 20,
    case_sensitive: bool = False,
    company: str | None = None,
    topic: str | None = None,
) -> list[SearchResult]:
    """Search all transcripts (or summaries) for the query."""
    results = []
    index_cache: dict = {}

    # Determine which directory to search
    if search_summaries:
        search_dir = SUMMARY_DIR
        pattern = "EP*_summary.txt"
        source = "summary"
    else:
        search_dir = TRANSCRIPT_DIR
        pattern = "EP*.txt"
        source = "transcript"

    if not search_dir.exists():
        return results

    for file_path in sorted(search_dir.glob(pattern)):
        ep_num = get_episode_number_from_filename(file_path.name)
        if ep_num is None:
            continue

        # Apply episode range filter
        if ep_start and ep_num < ep_start:
            continue
        if ep_end and ep_num > ep_end:
            continue

        for result in search_file(
            file_path, query, source, case_sensitive,
            index_cache=index_cache, company_filter=company, topic_filter=topic,
        ):
            results.append(result)
            if len(results) >= limit:
                return results

    return results


def highlight_match(text: str, matched_text: str, use_color: bool = True) -> str:
    """Highlight the matched text in the line."""
    if not use_color:
        return text

    # Case-insensitive replacement that preserves original case
    pattern = re.compile(re.escape(matched_text), re.IGNORECASE)
    return pattern.sub(
        lambda m: f"{HIGHLIGHT_START}{m.group(0)}{HIGHLIGHT_END}",
        text
    )


def format_results_text(results: list[SearchResult], query: str, use_color: bool = True) -> str:
    """Format results for terminal output."""
    if not results:
        return f"No results found for '{query}'"

    lines = [f"Found {len(results)} result(s) for '{query}':", ""]

    current_ep = None
    for r in results:
        # Show episode header when it changes
        if r.episode_number != current_ep:
            if current_ep is not None:
                lines.append("")
            lines.append(f"EP{r.episode_number:04d}:")
            current_ep = r.episode_number

        # Format the result line
        if r.timestamp:
            prefix = f"  [{r.timestamp}]"
        else:
            prefix = f"  (line {r.line_number})"

        highlighted = highlight_match(r.text, r.matched_text, use_color)
        line = f"{prefix} {highlighted}"
        if r.company or r.topic:
            tags = []
            if r.company:
                tags.append(f"company: {r.company}")
            if r.topic:
                tags.append(f"topic: {r.topic}")
            line += f"  ({', '.join(tags)})"
        lines.append(line)

    return "\n".join(lines)


def format_results_json(results: list[SearchResult]) -> str:
    """Format results as JSON."""
    output = [
        {
            "episode": r.episode_number,
            "timestamp": r.timestamp,
            "line": r.line_number,
            "text": r.text,
            "source": r.source,
            "company": r.company,
            "topic": r.topic,
        }
        for r in results
    ]
    return json.dumps(output, ensure_ascii=False, indent=2)


def main():
    parser = argparse.ArgumentParser(
        description="Search Gooaye transcripts",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python search.py "台積電"                  Search all transcripts
  python search.py "台積電" --ep 620-630     Search specific episodes
  python search.py "NVDA" --summary          Search summaries only
  python search.py "ETF" --limit 50          Show up to 50 results
  python search.py "聯準會" --json           Output as JSON
"""
    )
    parser.add_argument('query', type=str, help="Search term")
    parser.add_argument('--ep', type=str, default=None,
                        help="Episode range (e.g., '620-630' or '620')")
    parser.add_argument('--summary', action='store_true',
                        help="Search summaries instead of transcripts")
    parser.add_argument('--limit', '-n', type=int, default=20,
                        help="Maximum results to show (default: 20)")
    parser.add_argument('--json', action='store_true',
                        help="Output as JSON")
    parser.add_argument('--case-sensitive', '-c', action='store_true',
                        help="Case-sensitive search")
    parser.add_argument('--no-color', action='store_true',
                        help="Disable colored output")
    parser.add_argument('--company', type=str, default=None,
                        help="Filter to windows tagged with this company (from the Jev index)")
    parser.add_argument('--topic', type=str, default=None,
                        help="Filter to windows whose topic contains this text (from the Jev index)")
    args = parser.parse_args()

    # Parse episode range
    ep_start, ep_end = None, None
    if args.ep:
        ep_start, ep_end = parse_episode_range(args.ep)

    # Detect if output is to terminal
    use_color = sys.stdout.isatty() and not args.no_color and not args.json

    # Perform search
    results = search_transcripts(
        query=args.query,
        ep_start=ep_start,
        ep_end=ep_end,
        search_summaries=args.summary,
        limit=args.limit,
        case_sensitive=args.case_sensitive,
        company=args.company,
        topic=args.topic,
    )

    # Output results
    if args.json:
        print(format_results_json(results))
    else:
        print(format_results_text(results, args.query, use_color))


if __name__ == "__main__":
    main()
