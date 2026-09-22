"""Jev (TypeSafe) indexing: per-window company/topic/view tags for search.

Moved out of the validated prototype at spike/jev_window_eval.py (that file
stays untouched — see its tests in spike/test_jev_window_eval.py). This
module always asks ONE window per request (never batched — batching 20
windows into one request was found to collapse every answer to `none`, see
Learned Rule 14 in CLAUDE.md), adding a third `topic` question alongside the
spike's `company`/`view` pair.

Network boundary is `post_request` — tests monkeypatch it, same pattern as
the spike (never hit the real API in tests).
"""
import concurrent.futures
import json
import os
import re
import ssl
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

import certifi

from src.config import DATA_DIR

# This venv's python.org framework build has no system CA bundle wired up
# (the classic "run Install Certificates.command" gap), so urllib's default
# SSL context fails every HTTPS call with CERTIFICATE_VERIFY_FAILED. Build
# the context from certifi's bundle explicitly instead of relying on the
# system default — verified against the real API 2026-09-22.
_SSL_CONTEXT = ssl.create_default_context(cafile=certifi.where())

API_URL = "https://api.typesafe.ai/v1/systemone"
MODEL = "jev-1.13.0"
INPUT_TOKEN_COST_PER_M = 0.042
MAX_WORKERS = 6

TOPICS_SECTION_HEADER = "### 主要討論話題"
CANDIDATES_SECTION_HEADER = "### 提到的股票/ETF/標的"

# Built-in alias groups for frequent Whisper mis-transcriptions and common
# names. First item in each group is the canonical display name.
# (copied verbatim from spike/jev_window_eval.py — keep both in sync by hand
# if either changes; the spike itself is not imported here so it can stay
# untouched.)
ALIAS_GROUPS = [
    ["台積電", "台積", "TSMC"],
    ["輝達", "NVIDIA", "Nvidia", "英偉達"],
    ["超微", "AMD"],
    ["美光", "Micron"],
    ["聯發科"],
    ["鴻海"],
    ["廣達"],
    ["緯穎"],
    ["台達電"],
    ["SpaceX"],
    ["Cerebras"],
    ["Tesla", "特斯拉"],
    ["Google", "谷歌"],
    ["Apple", "蘋果"],
    ["Microsoft", "微軟"],
    ["Amazon", "亞馬遜"],
    ["Broadcom", "博通"],
    ["Marvell"],
    ["SK海力士", "海力士"],
    ["三星"],
]

ALIAS_LOOKUP = {
    term: group[0] for group in ALIAS_GROUPS for term in group
}


# ---------------------------------------------------------------------------
# Windowing
# ---------------------------------------------------------------------------

def build_windows(segments, window_seconds=60):
    """Group consecutive Whisper segments into windows spanning >= window_seconds."""
    windows = []
    current = []
    window_start = None
    for seg in segments:
        if not current:
            window_start = seg["start"]
        current.append(seg)
        if seg["end"] - window_start >= window_seconds:
            windows.append(_finalize_window(current, len(windows) + 1))
            current = []
            window_start = None
    if current:
        windows.append(_finalize_window(current, len(windows) + 1))
    return windows


def _finalize_window(segs, idx):
    return {
        "idx": idx,
        "start": segs[0]["start"],
        "end": segs[-1]["end"],
        "text": " ".join(s["text"] for s in segs),
    }


# ---------------------------------------------------------------------------
# Candidate (company) parsing
# ---------------------------------------------------------------------------

def _parse_summary_candidate_names(summary_text):
    """Names before ' - ' on each '- ' bullet under 提到的股票/ETF/標的."""
    names = []
    seen = set()
    in_section = False
    for line in summary_text.splitlines():
        if line.strip() == CANDIDATES_SECTION_HEADER:
            in_section = True
            continue
        if not in_section:
            continue
        if line.startswith("### ") or line.strip().startswith("---"):
            break
        stripped = line.strip()
        if not stripped.startswith("- "):
            continue
        bullet = stripped[2:].strip()
        name = bullet.split(" - ", 1)[0].strip().strip("*").strip()
        if name and name not in seen:
            seen.add(name)
            names.append(name)
    return names


def parse_candidates(summary_text):
    """Deduplicated company display names: summary bullets (canonicalized
    through the alias table) plus any alias-table names not already covered."""
    candidates = []
    seen = set()
    for name in _parse_summary_candidate_names(summary_text):
        canonical = ALIAS_LOOKUP.get(name, name)
        if canonical not in seen:
            seen.add(canonical)
            candidates.append(canonical)
    for group in ALIAS_GROUPS:
        canonical = group[0]
        if canonical not in seen:
            seen.add(canonical)
            candidates.append(canonical)
    return candidates


def _alias_display(canonical):
    for group in ALIAS_GROUPS:
        if group[0] == canonical:
            return "/".join(group[1:])
    return ""


def build_criteria(candidates):
    criteria = {
        name: f"the company {name} (also written as: {_alias_display(name)})"
        for name in candidates
    }
    criteria["none"] = "no single company is the main subject"
    return criteria


# ---------------------------------------------------------------------------
# Topic parsing
# ---------------------------------------------------------------------------

def parse_topics(summary_text):
    """The `####` headings under the summary's 主要討論話題 section, stripped
    of markdown, deduplicated, in order.

    Boundary check is a literal string prefix ("### " / "#### ", both with
    the trailing space) rather than a regex — see tests/test_summary_topics.py
    Rule (2026-08-21) for why "\\n###" carelessly matching "\\n####" truncated
    a topics section before.
    """
    topics = []
    seen = set()
    in_section = False
    for line in summary_text.splitlines():
        stripped = line.strip()
        if stripped == TOPICS_SECTION_HEADER:
            in_section = True
            continue
        if not in_section:
            continue
        if stripped.startswith("### ") or stripped.startswith("---"):
            break
        title = _topic_title(stripped)
        if title and title not in seen:
            seen.add(title)
            topics.append(title)
    return topics


_BOLD_BULLET_RE = re.compile(r"^[-*]\s+\*\*(?P<title>.+?)\*\*\s*$")
_BOLD_NUMBERED_RE = re.compile(r"^(?:\*\*)?\s*\d+[\.、]\s*(?:\*\*)?(?P<title>[^*]+?)(?:\*\*)?\s*$")


def _topic_title(stripped: str) -> str | None:
    """Topic titles appear in three shapes across the summaries (2026-09-22
    audit of 78 gooaye files): `#### title` (EP0688, 1 file), `- **title**` /
    `*   **title**` (most files), and `**1. title**` / `1. **title**`
    (numbered). A plain bullet (`- prose`) or a prose line is never a title,
    which is what keeps sub-bullets and body text out."""
    if stripped.startswith("#### "):
        return stripped[len("#### "):].strip().strip("*").strip() or None
    m = _BOLD_BULLET_RE.match(stripped)
    if m:
        title = re.sub(r"^\d+[\.、]\s*", "", m.group("title").strip()).strip()
        return title or None
    if stripped.startswith("**") or re.match(r"^\d+[\.、]\s*\*\*", stripped):
        m = _BOLD_NUMBERED_RE.match(stripped)
        if m:
            return m.group("title").strip() or None
    return None


# ---------------------------------------------------------------------------
# Request building — always one window per request (unkeyed `window.text`)
# ---------------------------------------------------------------------------

# The live API rejects a noul question with no criteria/instructions
# ("Noul question must have criteria or instructions") — undocumented in the
# API spec we were given, found by a real call (see spike).
VIEW_INSTRUCTIONS = (
    "In `window.text`, score 1.0 if the host gives his own opinion, forecast, or "
    "buy/sell/hold-style recommendation about a company, stock, sector, or "
    "the market. Score 0.0 if the text is about fitness, family, "
    "listeners' personal questions, sponsors, or life advice, or only "
    "reports facts, news, or what other people said with no market view of "
    "the host's own."
)


def _company_question(criteria):
    return {
        "type": "choice",
        "instructions": (
            "Which company is `window.text` mainly about? Choose `none` if "
            "no single company is the main subject or the window is about "
            "the host's personal life, listener questions, sponsors, or "
            "general market mood."
        ),
        "criteria": criteria,
    }


def _topic_question(topics):
    criteria = {t: t for t in topics}
    criteria["none"] = "none of these topics"
    return {
        "type": "choice",
        "instructions": (
            "Which of these topics from the episode summary is "
            "`window.text` mainly about? Choose `none` if it is about none "
            "of them (host's personal life, listener letters, sponsors)."
        ),
        "criteria": criteria,
    }


def _view_question():
    return {
        "type": "noul",
        "instructions": VIEW_INSTRUCTIONS,
    }


def build_request(window_text, candidates, topics, model=MODEL):
    """One request, one window, three questions: company / topic / view."""
    criteria = build_criteria(candidates)
    return {
        "model": model,
        "state": {"window": {"text": window_text}},
        "questions": {
            "company": _company_question(criteria),
            "topic": _topic_question(topics),
            "view": _view_question(),
        },
    }


# ---------------------------------------------------------------------------
# Network (single boundary — monkeypatch post_request in tests)
# ---------------------------------------------------------------------------

def post_request(payload, api_key, timeout=60):
    req = urllib.request.Request(
        API_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout, context=_SSL_CONTEXT) as resp:
        return json.loads(resp.read().decode("utf-8"))


def call_request(payload, api_key):
    """POST once; on any error, wait 2s and retry once; else return None."""
    try:
        return post_request(payload, api_key)
    except Exception:
        time.sleep(2)
        try:
            return post_request(payload, api_key)
        except Exception:
            return None


def extract_answers(response):
    if not response:
        return {}
    answers = response.get("answers")
    if isinstance(answers, dict):
        return answers
    return {k: v for k, v in response.items() if k not in ("usage", "model")}


def _apply_answer(window, answers):
    company_ans = answers.get("company")
    topic_ans = answers.get("topic")
    view_ans = answers.get("view")
    return {
        "idx": window["idx"],
        "start": window["start"],
        "end": window["end"],
        "company": company_ans.get("choice", "error") if company_ans else "error",
        "company_conf": company_ans.get("confidence") if company_ans else None,
        "topic": topic_ans.get("choice", "error") if topic_ans else "error",
        "topic_conf": topic_ans.get("confidence") if topic_ans else None,
        "view": view_ans.get("noul") if view_ans else None,
        "text": window["text"],
    }


def _ask_one_window(window, candidates, topics, api_key):
    payload = build_request(window["text"], candidates, topics)
    response = call_request(payload, api_key)
    answers = extract_answers(response)
    input_tokens = response.get("usage", {}).get("input_tokens", 0) if response else 0
    return _apply_answer(window, answers), input_tokens


def ask_windows(windows, candidates, topics, api_key, max_workers=6):
    """POST one request per window (never batched), max_workers concurrent.

    Returns (results, usage): results sorted by idx, usage is
    {"input_tokens", "cost_usd"}. A window whose request fails (both the
    try and the retry) comes back with company="error", topic="error",
    view=None — see _apply_answer.
    """
    results_by_idx = {}
    total_input_tokens = 0
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = [
            executor.submit(_ask_one_window, w, candidates, topics, api_key)
            for w in windows
        ]
        for future in concurrent.futures.as_completed(futures):
            row, input_tokens = future.result()
            results_by_idx[row["idx"]] = row
            total_input_tokens += input_tokens
    results = [results_by_idx[i] for i in sorted(results_by_idx)]
    cost = total_input_tokens * INPUT_TOKEN_COST_PER_M / 1_000_000
    return results, {"input_tokens": total_input_tokens, "cost_usd": cost}


# ---------------------------------------------------------------------------
# Episode-level entry point
# ---------------------------------------------------------------------------

def index_episode(
    podcast: str,
    episode_id: str,
    api_key: str | None = None,
    window_seconds: int = 60,
    max_workers: int = MAX_WORKERS,
    data_dir: Path | None = None,
) -> dict:
    """Index one episode's transcript with Jev and write the index JSON.

    Reads data/{podcast}/transcripts/{episode_id}.json and
    data/{podcast}/summaries/{episode_id}_summary.txt (or under `data_dir`
    if given), writes data/{podcast}/index/{episode_id}.json, and returns
    the same dict.

    Raises on a missing/unreadable transcript or summary (a programming/data
    error — callers should let this propagate) and on a full Jev outage for
    this episode (every window's request failed — callers should treat this
    as the "loud but non-fatal" WARNING-and-skip case, not write output).
    """
    if api_key is None:
        api_key = os.environ.get("TYPESAFE_API_KEY")

    base_data_dir = Path(data_dir) if data_dir is not None else (DATA_DIR / podcast)
    transcript_path = base_data_dir / "transcripts" / f"{episode_id}.json"
    summary_path = base_data_dir / "summaries" / f"{episode_id}_summary.txt"

    segments = json.loads(transcript_path.read_text(encoding="utf-8"))
    summary_text = summary_path.read_text(encoding="utf-8")

    windows = build_windows(segments, window_seconds)
    candidates = parse_candidates(summary_text)
    topics = parse_topics(summary_text)

    results, usage = ask_windows(windows, candidates, topics, api_key, max_workers=max_workers)

    if results and all(r["company"] == "error" for r in results):
        raise RuntimeError(
            f"Jev index failed for all {len(results)} window(s) in {episode_id} "
            "(check TYPESAFE_API_KEY / API status)"
        )

    output = {
        "episode_id": episode_id,
        "podcast": podcast,
        "model": MODEL,
        "window_seconds": window_seconds,
        "candidates": candidates,
        "topics": topics,
        "windows": results,
        "usage": usage,
        "indexed_at": datetime.now(timezone.utc).isoformat(),
    }

    index_dir = base_data_dir / "index"
    index_dir.mkdir(parents=True, exist_ok=True)
    index_path = index_dir / f"{episode_id}.json"
    index_path.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")

    return output
