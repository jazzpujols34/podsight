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

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from config import DATA_DIR, TRANSCRIPT_DIR

SUMMARY_DIR = DATA_DIR / "summaries"

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


def get_episode_number_from_filename(filename: str) -> int | None:
    """Extract episode number from filename like EP0621.txt"""
    match = re.search(r'EP(\d+)', filename)
    return int(match.group(1)) if match else None


def parse_timestamp(line: str) -> str:
    """Extract timestamp from line like '[07:25] text...'"""
    match = re.match(r'\[(\d+:\d+)\]', line)
    return match.group(1) if match else ""


def search_file(
    file_path: Path,
    query: str,
    source: str,
    case_sensitive: bool = False
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

    for line_num, line in enumerate(content.split('\n'), 1):
        if pattern.search(line):
            timestamp = parse_timestamp(line) if source == "transcript" else ""

            # Find the actual matched text for highlighting
            match = pattern.search(line)
            matched_text = match.group(0) if match else query

            yield SearchResult(
                episode_number=ep_num,
                timestamp=timestamp,
                line_number=line_num,
                text=line.strip(),
                matched_text=matched_text,
                source=source
            )


def search_transcripts(
    query: str,
    ep_start: int | None = None,
    ep_end: int | None = None,
    search_summaries: bool = False,
    limit: int = 20,
    case_sensitive: bool = False
) -> list[SearchResult]:
    """Search all transcripts (or summaries) for the query."""
    results = []

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

        for result in search_file(file_path, query, source, case_sensitive):
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
        lines.append(f"{prefix} {highlighted}")

    return "\n".join(lines)


def format_results_json(results: list[SearchResult]) -> str:
    """Format results as JSON."""
    output = [
        {
            "episode": r.episode_number,
            "timestamp": r.timestamp,
            "line": r.line_number,
            "text": r.text,
            "source": r.source
        }
        for r in results
    ]
    return json.dumps(output, ensure_ascii=False, indent=2)


def parse_episode_range(range_str: str) -> tuple[int | None, int | None]:
    """Parse episode range like '620-625' or '620'."""
    if '-' in range_str:
        parts = range_str.split('-')
        return int(parts[0]), int(parts[1])
    else:
        ep = int(range_str)
        return ep, ep


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
        case_sensitive=args.case_sensitive
    )

    # Output results
    if args.json:
        print(format_results_json(results))
    else:
        print(format_results_text(results, args.query, use_color))


if __name__ == "__main__":
    main()
