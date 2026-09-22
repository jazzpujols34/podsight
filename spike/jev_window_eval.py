"""Offline evaluation spike: TypeSafe Jev vs. ~60s transcript windows.

For one gooaye episode, builds ~60s windows from the Whisper segment list,
asks the Jev model which company (if any) each window is mainly about and
whether the host states his own view in it, then prints a Markdown table a
human grades by eye. Read-only: changes nothing in the pipeline.

    python3 spike/jev_window_eval.py EP0688 [--podcast gooaye]
                                             [--window-seconds 60]
                                             [--chunk 1] [--dry-run]

--chunk controls how many windows share one API request (default 1: one
window per request, each its own unkeyed `window.text` state — batching many
windows into one keyed `windows.w{i}` request was found to degrade Jev's
per-window accuracy, see EP0688_windows.json vs EP0688_windows_chunk1.json).
Requests run concurrently, 6 at a time.

Requires TYPESAFE_API_KEY in the environment (never printed).
"""
from __future__ import annotations

import argparse
import concurrent.futures
import json
import os
import sys
import time
import urllib.error
import urllib.request
from collections import Counter
from pathlib import Path

API_URL = "https://api.typesafe.ai/v1/systemone"
MODEL = "jev-1.13.0"
CHUNK_SIZE = 20
SMALL_CHUNK_SIZE = 10
MAX_STATE_CHARS = 40_000
INPUT_TOKEN_COST_PER_M = 0.042
MAX_WORKERS = 6

SECTION_HEADER = "### 提到的股票/ETF/標的"

# Built-in alias groups for frequent Whisper mis-transcriptions and common
# names. First item in each group is the canonical display name.
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
    """Group consecutive segments into windows spanning >= window_seconds."""
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
# Candidate parsing
# ---------------------------------------------------------------------------

def parse_summary_candidates(summary_text):
    """Names before ' - ' on each '- ' bullet under 提到的股票/ETF/標的."""
    names = []
    seen = set()
    in_section = False
    for line in summary_text.splitlines():
        if line.strip() == SECTION_HEADER:
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


def build_candidates(summary_text):
    """Deduplicated display names: summary bullets, canonicalized through the
    alias table, then any alias-table names not already covered."""
    candidates = []
    seen = set()
    for name in parse_summary_candidates(summary_text):
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
# Request building
# ---------------------------------------------------------------------------

def build_state(chunk):
    return {"windows": {f"w{w['idx']}": {"text": w["text"]} for w in chunk}}


# The live API rejects a noul question with no criteria/instructions
# ("Noul question must have criteria or instructions") — undocumented in the
# API spec we were given, found by a real call.
VIEW_INSTRUCTIONS = (
    "Score 1.0 if the host gives his own opinion, forecast, or "
    "buy/sell/hold-style recommendation about a company, stock, sector, or "
    "the market. Score 0.0 if the text is about fitness, family, "
    "listeners' personal questions, sponsors, or life advice, or only "
    "reports facts, news, or what other people said with no market view of "
    "the host's own."
)


def _question_pair(text_ref, criteria):
    """Build the (company, view) question objects referencing text_ref
    (e.g. "windows.w3.text" or "window.text")."""
    company_q = {
        "type": "choice",
        "text": (
            f"Which company is {text_ref} mainly about? Choose `none` if "
            "no single company is the main subject or the window is about "
            "the host's personal life, listener questions, sponsors, or "
            "general market mood."
        ),
        "criteria": criteria,
    }
    view_q = {
        "type": "noul",
        "text": (
            f"In {text_ref} the host gives his own opinion, forecast, or "
            "buy/sell/hold-style recommendation about a specific company, "
            "stock, sector, or the stock market. Talk about fitness, "
            "family, listeners' personal questions, sponsors, or life "
            "advice is NOT a market view."
        ),
        "instructions": VIEW_INSTRUCTIONS,
    }
    return company_q, view_q


def build_window_questions(window, criteria):
    i = window["idx"]
    company_q, view_q = _question_pair(f"windows.w{i}.text", criteria)
    return {f"w{i}_company": company_q, f"w{i}_view": view_q}


def build_single_window_questions(criteria):
    company_q, view_q = _question_pair("window.text", criteria)
    return {"company": company_q, "view": view_q}


def build_chunk_payload(chunk, criteria, model=MODEL):
    """Keyed multi-window payload (windows.w1, windows.w2, ... — chunk > 1)."""
    questions = {}
    for w in chunk:
        questions.update(build_window_questions(w, criteria))
    return {"model": model, "state": build_state(chunk), "questions": questions}


def build_single_window_payload(window, criteria, model=MODEL):
    """Unkeyed single-window payload (chunk == 1): state is `window.text`,
    questions are plain `company` / `view`."""
    return {
        "model": model,
        "state": {"window": {"text": window["text"]}},
        "questions": build_single_window_questions(criteria),
    }


def iter_chunks(windows, criteria, chunk_size=CHUNK_SIZE,
                 max_state_chars=MAX_STATE_CHARS):
    """Yield window chunks, shrinking the chunk size if a chunk's state
    (alone, not the full payload) would exceed max_state_chars."""
    i = 0
    size = chunk_size
    n = len(windows)
    while i < n:
        chunk = windows[i:i + size]
        state_chars = len(json.dumps(build_state(chunk), ensure_ascii=False))
        if state_chars > max_state_chars and size > SMALL_CHUNK_SIZE:
            size = SMALL_CHUNK_SIZE
            continue
        yield chunk
        i += len(chunk)


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
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def call_chunk(payload, api_key):
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


def apply_answers(chunk, response_or_answers, results, unkeyed=False):
    """Fill results with one row per window. response_or_answers is None on
    a fully failed chunk (both attempts errored) -> company="error".
    unkeyed=True reads the "company"/"view" keys used when chunk==1, instead
    of the keyed "w{i}_company"/"w{i}_view" keys."""
    if response_or_answers is None:
        answers = {}
        failed = True
    else:
        answers = response_or_answers
        failed = False
    for w in chunk:
        i = w["idx"]
        company_key = "company" if unkeyed else f"w{i}_company"
        view_key = "view" if unkeyed else f"w{i}_view"
        company_ans = answers.get(company_key)
        view_ans = answers.get(view_key)
        if failed or company_ans is None:
            company, conf = "error", None
        else:
            company, conf = company_ans.get("choice", "error"), company_ans.get("confidence")
        view = view_ans.get("noul") if (view_ans and not failed) else None
        results.append({
            "idx": i,
            "start": w["start"],
            "end": w["end"],
            "company": company,
            "company_conf": conf,
            "view": view,
            "text": w["text"],
        })


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------

def format_mmss(seconds):
    total = int(seconds)
    return f"{total // 60:02d}:{total % 60:02d}"


def format_table(results):
    lines = [
        "| idx | mm:ss | company (conf) | view | text (first 60 chars) |",
        "|---|---|---|---|---|",
    ]
    for r in results:
        if r["company"] == "error":
            company_col = "error"
        else:
            conf = r["company_conf"]
            conf_str = f"{conf:.2f}" if isinstance(conf, (int, float)) else "-"
            company_col = f"{r['company']} ({conf_str})"
        view = r["view"]
        view_col = f"{view:.2f}" if isinstance(view, (int, float)) else "-"
        text = r["text"][:60].replace("\n", " ").replace("|", "/")
        if len(r["text"]) > 60:
            text += "…"
        lines.append(f"| {r['idx']} | {format_mmss(r['start'])} | {company_col} | {view_col} | {text} |")
    return "\n".join(lines)


def format_summary_line(results):
    counts = Counter(r["company"] for r in results)
    counts_str = ", ".join(f"{name}={n}" for name, n in sorted(counts.items()))
    view_ge_half = sum(
        1 for r in results if isinstance(r["view"], (int, float)) and r["view"] >= 0.5
    )
    return f"counts: {counts_str} | view>=0.5: {view_ge_half}/{len(results)}"


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _process_chunk(chunk, criteria, chunk_size, api_key):
    if chunk_size == 1:
        payload = build_single_window_payload(chunk[0], criteria)
    else:
        payload = build_chunk_payload(chunk, criteria)
    response = call_chunk(payload, api_key)
    return chunk, response


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("episode")
    parser.add_argument("--podcast", default="gooaye")
    parser.add_argument("--window-seconds", type=int, default=60)
    parser.add_argument("--chunk", type=int, default=1,
                         help="windows per API request (default 1: one "
                              "window per request, unkeyed window.text state)")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    base = Path(__file__).resolve().parent.parent
    transcript_path = base / "data" / args.podcast / "transcripts" / f"{args.episode}.json"
    summary_path = base / "data" / args.podcast / "summaries" / f"{args.episode}_summary.txt"

    segments = json.loads(transcript_path.read_text(encoding="utf-8"))
    summary_text = summary_path.read_text(encoding="utf-8")

    windows = build_windows(segments, args.window_seconds)
    candidates = build_candidates(summary_text)
    criteria = build_criteria(candidates)

    chunks = list(iter_chunks(windows, criteria, chunk_size=args.chunk))

    if args.dry_run:
        first_chunk = chunks[0] if chunks else []
        if args.chunk == 1 and first_chunk:
            payload = build_single_window_payload(first_chunk[0], criteria)
        else:
            payload = build_chunk_payload(first_chunk, criteria)
        payload_chars = len(json.dumps(payload, ensure_ascii=False))
        print(f"windows: {len(windows)}")
        print(f"candidates ({len(candidates)}): {', '.join(candidates)}")
        print(f"first chunk payload chars: {payload_chars}")
        return

    api_key = os.environ.get("TYPESAFE_API_KEY")
    if not api_key:
        print("TYPESAFE_API_KEY not set in environment", file=sys.stderr)
        sys.exit(1)

    unkeyed = args.chunk == 1
    results_by_idx = {}
    total_input_tokens = 0
    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = [
            executor.submit(_process_chunk, chunk, criteria, args.chunk, api_key)
            for chunk in chunks
        ]
        for future in concurrent.futures.as_completed(futures):
            chunk, response = future.result()
            answers = extract_answers(response)
            chunk_results = []
            apply_answers(chunk, answers if response else None, chunk_results, unkeyed=unkeyed)
            for r in chunk_results:
                results_by_idx[r["idx"]] = r
            if response:
                total_input_tokens += response.get("usage", {}).get("input_tokens", 0)

    results = [results_by_idx[i] for i in sorted(results_by_idx)]

    out_dir = base / "spike" / "out"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{args.episode}_windows_chunk{args.chunk}.json"
    out_path.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")

    print(format_table(results))
    print(format_summary_line(results))
    cost = total_input_tokens * INPUT_TOKEN_COST_PER_M / 1_000_000
    print(f"\ninput_tokens: {total_input_tokens}")
    print(f"estimated_cost_usd: ${cost:.4f}")


if __name__ == "__main__":
    main()
