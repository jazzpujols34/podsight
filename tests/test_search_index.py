"""Tests for search.py's Jev-index integration (src/pipeline/search.py).

A search result shows the company/topic of the Jev-index window covering its
timestamp, and --company/--topic filter on that. Never touches the real
data/ dir — TRANSCRIPT_DIR/INDEX_DIR are monkeypatched to tmp_path.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.pipeline import search  # noqa: E402

TRANSCRIPT_TEXT = (
    "[00:05] 大家好歡迎收聽\n"
    "[00:30] SpaceX 這次解禁其實影響不大\n"
    "[01:20] 800V 架構是接下來的重點\n"
    "[02:10] 謝謝大家收聽再見\n"
)

INDEX_DATA = {
    "episode_id": "EP0688",
    "podcast": "gooaye",
    "model": "jev-1.13.0",
    "window_seconds": 60,
    "candidates": ["SpaceX", "輝達"],
    "topics": ["NVIDIA 800V 架構"],
    "windows": [
        {"idx": 1, "start": 0, "end": 60, "company": "SpaceX", "company_conf": 0.9,
         "topic": "none", "topic_conf": 0.7, "view": 0.2, "text": "..."},
        {"idx": 2, "start": 60, "end": 120, "company": "none", "company_conf": 0.6,
         "topic": "NVIDIA 800V 架構", "topic_conf": 0.85, "view": 0.4, "text": "..."},
        {"idx": 3, "start": 120, "end": 150, "company": "none", "company_conf": 0.5,
         "topic": "none", "topic_conf": 0.5, "view": 0.1, "text": "..."},
    ],
    "usage": {"input_tokens": 1000, "cost_usd": 0.000042},
    "indexed_at": "2026-09-22T00:00:00+00:00",
}


def _setup(tmp_path, monkeypatch, write_index=True):
    transcript_dir = tmp_path / "transcripts"
    index_dir = tmp_path / "index"
    transcript_dir.mkdir()
    index_dir.mkdir()
    (transcript_dir / "EP0688.txt").write_text(TRANSCRIPT_TEXT, encoding="utf-8")
    if write_index:
        (index_dir / "EP0688.json").write_text(
            json.dumps(INDEX_DATA, ensure_ascii=False), encoding="utf-8"
        )
    monkeypatch.setattr(search, "TRANSCRIPT_DIR", transcript_dir)
    monkeypatch.setattr(search, "INDEX_DIR", index_dir)


def test_search_result_shows_company_and_topic_from_index(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)

    results = search.search_transcripts("SpaceX")
    assert len(results) == 1
    assert results[0].company == "SpaceX"
    assert results[0].topic == "none"

    results = search.search_transcripts("800V")
    assert len(results) == 1
    assert results[0].company == "none"
    assert results[0].topic == "NVIDIA 800V 架構"


def test_search_result_company_topic_none_when_no_index(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch, write_index=False)

    results = search.search_transcripts("SpaceX")
    assert len(results) == 1
    assert results[0].company is None
    assert results[0].topic is None


def test_company_filter_restricts_to_matching_windows(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)

    # "收聽" appears in windows 1 (00:05, company=SpaceX) and 4 (02:10, window 3, company=none)
    all_results = search.search_transcripts("收聽")
    assert len(all_results) == 2

    filtered = search.search_transcripts("收聽", company="none")
    assert len(filtered) == 1
    assert filtered[0].timestamp == "02:10"
    assert filtered[0].company == "none"


def test_topic_filter_is_case_insensitive_substring(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)

    filtered = search.search_transcripts("架構", topic="800v")
    assert len(filtered) == 1
    assert filtered[0].topic == "NVIDIA 800V 架構"


def test_json_output_includes_company_and_topic_keys():
    result = search.SearchResult(
        episode_number=688, timestamp="00:30", line_number=2, text="text",
        matched_text="SpaceX", source="transcript", company="SpaceX", topic="none",
    )
    output = json.loads(search.format_results_json([result]))
    assert output[0]["company"] == "SpaceX"
    assert output[0]["topic"] == "none"
