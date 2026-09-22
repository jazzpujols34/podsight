"""Tests for the offline 60s-window Jev eval spike (spike/jev_window_eval.py).

Pure functions only — windowing, candidate parsing, and request building.
No network: the HTTP boundary (`post_request`) is monkeypatched.
"""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

import jev_window_eval as jwe  # noqa: E402


FIXTURE_SUMMARY = """### 一句話總結
測試用摘要一句話。

### 主要討論話題

#### 隨便一個話題
- 內容不重要。

### 提到的股票/ETF/標的
- SpaceX - 股票解禁後未如預期崩跌，流動性增加後打底向上。
- Cerebras - 大尺寸晶片公司，與 AMD 合作。
- AMD - 與 Cerebras 合作，並透過收購將模型邏輯寫入晶片。

### 謝孟恭 (MK) 的觀點或金句
- 「這句不該被當成標的。」
"""


def make_segments(n, seg_len=15.0):
    return [
        {"start": i * seg_len, "end": (i + 1) * seg_len, "text": f"seg{i}"}
        for i in range(n)
    ]


# ---------------------------------------------------------------------------
# Windowing
# ---------------------------------------------------------------------------

def test_build_windows_groups_by_60s_span():
    segments = make_segments(10, seg_len=15.0)  # 10 x 15s = 150s
    windows = jwe.build_windows(segments, window_seconds=60)

    assert len(windows) == 3
    assert [w["idx"] for w in windows] == [1, 2, 3]

    # first two windows: 4 segments each, spanning exactly 60s
    assert windows[0]["start"] == 0.0
    assert windows[0]["end"] == 60.0
    assert windows[1]["start"] == 60.0
    assert windows[1]["end"] == 120.0

    # last window is shorter (only 2 segments left)
    assert windows[2]["start"] == 120.0
    assert windows[2]["end"] == 150.0
    assert (windows[2]["end"] - windows[2]["start"]) < 60


def test_build_windows_boundaries_are_contiguous():
    segments = make_segments(10, seg_len=15.0)
    windows = jwe.build_windows(segments, window_seconds=60)
    for a, b in zip(windows, windows[1:]):
        assert a["end"] == b["start"]


def test_build_windows_text_joined_with_space():
    segments = make_segments(10, seg_len=15.0)
    windows = jwe.build_windows(segments, window_seconds=60)
    assert windows[0]["text"] == "seg0 seg1 seg2 seg3"
    assert windows[1]["text"] == "seg4 seg5 seg6 seg7"
    assert windows[2]["text"] == "seg8 seg9"


def test_build_windows_1_based_idx():
    segments = make_segments(4, seg_len=15.0)
    windows = jwe.build_windows(segments, window_seconds=60)
    assert len(windows) == 1
    assert windows[0]["idx"] == 1


# ---------------------------------------------------------------------------
# Candidate parsing
# ---------------------------------------------------------------------------

def test_parse_summary_candidates_extracts_three_names():
    names = jwe.parse_summary_candidates(FIXTURE_SUMMARY)
    assert names == ["SpaceX", "Cerebras", "AMD"]


def test_parse_summary_candidates_stops_at_next_section():
    names = jwe.parse_summary_candidates(FIXTURE_SUMMARY)
    assert "這句不該被當成標的" not in names
    assert len(names) == 3


def test_alias_table_maps_variants_to_same_display_name():
    assert jwe.ALIAS_LOOKUP["輝達"] == jwe.ALIAS_LOOKUP["英偉達"]
    assert jwe.ALIAS_LOOKUP["輝達"] == jwe.ALIAS_LOOKUP["NVIDIA"]
    assert jwe.ALIAS_LOOKUP["輝達"] == jwe.ALIAS_LOOKUP["Nvidia"]


def test_build_candidates_merges_summary_and_alias_table_without_dupes():
    candidates = jwe.build_candidates(FIXTURE_SUMMARY)
    # summary-parsed names present as-is when they aren't an alias of anything
    assert "SpaceX" in candidates
    assert "Cerebras" in candidates
    # summary said "AMD", which the alias table canonicalizes to "超微" —
    # aliases map TO a display name, they aren't separate candidates
    assert "AMD" not in candidates
    assert "超微" in candidates
    # built-in alias-table names present even though not in the summary
    assert "台積電" in candidates
    assert "輝達" in candidates
    # SpaceX is both summary-parsed and its own alias-table group -> only once
    assert candidates.count("SpaceX") == 1
    # 超微 (from summary's "AMD") not duplicated with the alias table's own 超微 group
    assert candidates.count("超微") == 1
    # no display name repeated
    assert len(candidates) == len(set(candidates))


# ---------------------------------------------------------------------------
# Request building
# ---------------------------------------------------------------------------

def _dummy_windows(n):
    return [
        {"idx": i, "start": float(i * 60), "end": float((i + 1) * 60), "text": f"window text {i}"}
        for i in range(1, n + 1)
    ]


@pytest.mark.parametrize(
    "chunk_size,expected_lengths",
    [
        (1, [1] * 25),
        (20, [20, 5]),
    ],
)
def test_iter_chunks_splits_by_chunk_size(chunk_size, expected_lengths):
    windows = _dummy_windows(25)
    candidates = jwe.build_candidates(FIXTURE_SUMMARY)
    criteria = jwe.build_criteria(candidates)

    chunks = list(jwe.iter_chunks(windows, criteria, chunk_size=chunk_size))

    assert [len(c) for c in chunks] == expected_lengths
    # idx values are contiguous, in order, and cover every window once
    flat_idx = [w["idx"] for c in chunks for w in c]
    assert flat_idx == list(range(1, 26))


def test_build_single_window_payload_uses_unkeyed_window_state():
    window = _dummy_windows(1)[0]
    candidates = jwe.build_candidates(FIXTURE_SUMMARY)
    criteria = jwe.build_criteria(candidates)

    payload = jwe.build_single_window_payload(window, criteria)

    assert payload["model"] == "jev-1.13.0"
    assert payload["state"] == {"window": {"text": "window text 1"}}
    assert set(payload["questions"].keys()) == {"company", "view"}
    assert payload["questions"]["company"]["type"] == "choice"
    assert "window.text" in payload["questions"]["company"]["text"]
    assert "none" in payload["questions"]["company"]["criteria"]
    assert payload["questions"]["view"]["type"] == "noul"
    assert "window.text" in payload["questions"]["view"]["text"]
    assert payload["questions"]["view"].get("instructions")


def test_build_chunk_payload_keyed_state_and_questions():
    windows = _dummy_windows(3)
    candidates = jwe.build_candidates(FIXTURE_SUMMARY)
    criteria = jwe.build_criteria(candidates)

    payload = jwe.build_chunk_payload(windows, criteria)

    assert payload["model"] == "jev-1.13.0"
    # keyed state, never array indexes
    assert set(payload["state"]["windows"].keys()) == {"w1", "w2", "w3"}
    assert payload["state"]["windows"]["w1"]["text"] == "window text 1"

    # one _company (choice) and one _view (noul) question per window
    assert len(payload["questions"]) == 6
    for i in (1, 2, 3):
        company_q = payload["questions"][f"w{i}_company"]
        view_q = payload["questions"][f"w{i}_view"]
        assert company_q["type"] == "choice"
        assert f"windows.w{i}.text" in company_q["text"]
        assert view_q["type"] == "noul"
        assert f"windows.w{i}.text" in view_q["text"]
        # live API rejects a noul question with no criteria/instructions
        assert view_q.get("instructions")

    # "none" choice always present
    assert "none" in payload["questions"]["w1_company"]["criteria"]


def test_build_criteria_includes_alias_text_and_none():
    candidates = jwe.build_candidates(FIXTURE_SUMMARY)
    criteria = jwe.build_criteria(candidates)
    assert criteria["none"] == "no single company is the main subject"
    assert "the company SpaceX" in criteria["SpaceX"]
    assert "the company 台積電" in criteria["台積電"]
    assert "台積" in criteria["台積電"] or "TSMC" in criteria["台積電"]


# ---------------------------------------------------------------------------
# No network in tests: monkeypatch the poster (post_request)
# ---------------------------------------------------------------------------

def test_call_chunk_returns_response_on_success(monkeypatch):
    calls = []

    def fake_post(payload, api_key, timeout=60):
        calls.append(payload)
        return {"answers": {"w1_company": {"choice": "SpaceX", "confidence": 0.9}}}

    monkeypatch.setattr(jwe, "post_request", fake_post)
    result = jwe.call_chunk({"model": "jev-1.13.0"}, "fake-key")

    assert result == {"answers": {"w1_company": {"choice": "SpaceX", "confidence": 0.9}}}
    assert len(calls) == 1


def test_call_chunk_retries_once_then_marks_error(monkeypatch):
    attempts = []

    def failing_post(payload, api_key, timeout=60):
        attempts.append(1)
        raise RuntimeError("boom")

    monkeypatch.setattr(jwe, "post_request", failing_post)
    monkeypatch.setattr(jwe.time, "sleep", lambda s: None)

    result = jwe.call_chunk({"model": "jev-1.13.0"}, "fake-key")

    assert result is None
    assert len(attempts) == 2  # one try + one retry


def test_apply_answers_marks_chunk_error_on_failed_response():
    windows = _dummy_windows(2)
    results = []
    jwe.apply_answers(windows, None, results)
    assert len(results) == 2
    assert all(r["company"] == "error" for r in results)
    assert all(r["view"] is None for r in results)


def test_apply_answers_extracts_choice_and_noul():
    windows = _dummy_windows(1)
    answers = {
        "w1_company": {"choice": "SpaceX", "confidence": 0.87},
        "w1_view": {"noul": 0.62},
    }
    results = []
    jwe.apply_answers(windows, answers, results)
    assert results[0]["company"] == "SpaceX"
    assert results[0]["company_conf"] == 0.87
    assert results[0]["view"] == 0.62
    assert results[0]["text"] == "window text 1"


def test_apply_answers_unkeyed_extracts_choice_and_noul():
    windows = _dummy_windows(1)
    answers = {
        "company": {"choice": "台積電", "confidence": 0.71},
        "view": {"noul": 0.33},
    }
    results = []
    jwe.apply_answers(windows, answers, results, unkeyed=True)
    assert results[0]["company"] == "台積電"
    assert results[0]["company_conf"] == 0.71
    assert results[0]["view"] == 0.33
