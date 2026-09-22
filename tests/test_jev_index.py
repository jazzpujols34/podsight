"""Tests for src/pipeline/jev_index.py — the Jev per-window indexing step.

Pure functions (windowing, candidate/topic parsing, request building) plus
index_episode with a monkeypatched network boundary (post_request), and the
06_index_jev.py step script's "loud but non-fatal" WARNING behavior.

No network: post_request is monkeypatched everywhere, same pattern as
spike/test_jev_window_eval.py. Never writes to the real data/ dir — every
test uses tmp_path (or an isolated data_dir override for index_episode).
"""
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.pipeline import jev_index as jix  # noqa: E402
import src.config as config  # noqa: E402

VENV_PYTHON = PROJECT_ROOT / "venv" / "bin" / "python"
STEP_SCRIPT = PROJECT_ROOT / "src" / "pipeline" / "06_index_jev.py"


FIXTURE_SUMMARY = """### 一句話總結
測試用摘要一句話。

### 主要討論話題

#### SpaceX 與 Cerebras 股票解禁與籌碼流動性
- 內容不重要。

#### NVIDIA 800V DC 白皮書與伺服器電源架構演進
- 內容不重要。

#### 抄底與市場心理學
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
# Windowing (reuse the spike's cases)
# ---------------------------------------------------------------------------

def test_build_windows_groups_by_60s_span():
    segments = make_segments(10, seg_len=15.0)  # 10 x 15s = 150s
    windows = jix.build_windows(segments, window_seconds=60)

    assert len(windows) == 3
    assert [w["idx"] for w in windows] == [1, 2, 3]
    assert windows[0]["start"] == 0.0
    assert windows[0]["end"] == 60.0
    assert windows[1]["start"] == 60.0
    assert windows[1]["end"] == 120.0
    assert windows[2]["start"] == 120.0
    assert windows[2]["end"] == 150.0
    assert (windows[2]["end"] - windows[2]["start"]) < 60


def test_build_windows_boundaries_are_contiguous():
    segments = make_segments(10, seg_len=15.0)
    windows = jix.build_windows(segments, window_seconds=60)
    for a, b in zip(windows, windows[1:]):
        assert a["end"] == b["start"]


def test_build_windows_text_joined_with_space():
    segments = make_segments(10, seg_len=15.0)
    windows = jix.build_windows(segments, window_seconds=60)
    assert windows[0]["text"] == "seg0 seg1 seg2 seg3"


# ---------------------------------------------------------------------------
# Candidate parsing
# ---------------------------------------------------------------------------

def test_parse_candidates_merges_summary_and_alias_table():
    candidates = jix.parse_candidates(FIXTURE_SUMMARY)
    assert "SpaceX" in candidates
    assert "Cerebras" in candidates
    # summary said "AMD", which the alias table canonicalizes to "超微"
    assert "AMD" not in candidates
    assert "超微" in candidates
    # built-in alias-table names present even though not in the summary
    assert "台積電" in candidates
    assert "輝達" in candidates
    assert len(candidates) == len(set(candidates))


# ---------------------------------------------------------------------------
# Topic parsing
# ---------------------------------------------------------------------------

def test_parse_topics_extracts_three_headings_in_order():
    topics = jix.parse_topics(FIXTURE_SUMMARY)
    assert topics == [
        "SpaceX 與 Cerebras 股票解禁與籌碼流動性",
        "NVIDIA 800V DC 白皮書與伺服器電源架構演進",
        "抄底與市場心理學",
    ]


def test_parse_topics_stops_at_next_section():
    topics = jix.parse_topics(FIXTURE_SUMMARY)
    assert not any("這句不該被當成標的" in t for t in topics)


def test_parse_topics_dedupes():
    summary = FIXTURE_SUMMARY.replace(
        "#### 抄底與市場心理學",
        "#### SpaceX 與 Cerebras 股票解禁與籌碼流動性",
    ).replace(
        "#### NVIDIA 800V DC 白皮書與伺服器電源架構演進",
        "#### SpaceX 與 Cerebras 股票解禁與籌碼流動性",
    )
    topics = jix.parse_topics(summary)
    assert topics == ["SpaceX 與 Cerebras 股票解禁與籌碼流動性"]


def test_parse_topics_bold_bullet_style_and_plain_bullets_ignored():
    # 77 of 78 gooaye summaries mark topics as "- **bold**" or "*   **bold**";
    # plain bullets, numbered-bold labels and prose are handled as documented
    # in jev_index._topic_title (2026-09-22 audit).
    summary = (
        "### 主要討論話題\n\n"
        "- **台股近期盤勢觀察**\n  - 內容。\n"
        "- 這是一句沒有粗體的說明。\n"
        "*   **第二個主題**\n"
        "**3. 第三個主題**\n"
        "4. **第四個主題**\n"
        "#### 第五個主題\n"
    )
    assert jix.parse_topics(summary) == [
        "台股近期盤勢觀察", "第二個主題", "第三個主題", "第四個主題", "第五個主題",
    ]


# ---------------------------------------------------------------------------
# Request building
# ---------------------------------------------------------------------------

def test_build_request_has_exactly_company_topic_view():
    candidates = jix.parse_candidates(FIXTURE_SUMMARY)
    topics = jix.parse_topics(FIXTURE_SUMMARY)

    payload = jix.build_request("window text", candidates, topics)

    assert payload["model"] == "jev-1.13.0"
    assert payload["state"] == {"window": {"text": "window text"}}
    assert set(payload["questions"].keys()) == {"company", "topic", "view"}

    assert payload["questions"]["company"]["type"] == "choice"
    assert "none" in payload["questions"]["company"]["criteria"]
    assert "window.text" in payload["questions"]["company"]["instructions"]

    assert payload["questions"]["topic"]["type"] == "choice"
    assert "none" in payload["questions"]["topic"]["criteria"]
    assert "window.text" in payload["questions"]["topic"]["instructions"]
    for t in topics:
        assert t in payload["questions"]["topic"]["criteria"]

    assert payload["questions"]["view"]["type"] == "noul"
    assert "window.text" in payload["questions"]["view"]["instructions"]
    assert payload["questions"]["view"].get("instructions")


# ---------------------------------------------------------------------------
# index_episode — mocked poster, tmp data dir
# ---------------------------------------------------------------------------

def _write_episode_fixture(data_dir: Path, episode_id: str):
    (data_dir / "transcripts").mkdir(parents=True, exist_ok=True)
    (data_dir / "summaries").mkdir(parents=True, exist_ok=True)
    segments = [{"start": 0.0, "end": 5.0, "text": "測試視窗文字"}]
    (data_dir / "transcripts" / f"{episode_id}.json").write_text(
        json.dumps(segments, ensure_ascii=False), encoding="utf-8"
    )
    (data_dir / "summaries" / f"{episode_id}_summary.txt").write_text(
        FIXTURE_SUMMARY, encoding="utf-8"
    )


def test_index_episode_writes_documented_json_shape(tmp_path, monkeypatch):
    episode_id = "EP_TEST"
    _write_episode_fixture(tmp_path, episode_id)

    def fake_post(payload, api_key, timeout=60):
        return {
            "answers": {
                "company": {"choice": "SpaceX", "confidence": 0.91, "probabilities": {}},
                "topic": {"choice": "抄底與市場心理學", "confidence": 0.77, "probabilities": {}},
                "view": {"noul": 0.62},
            },
            "usage": {"input_tokens": 500},
        }

    monkeypatch.setattr(jix, "post_request", fake_post)

    result = jix.index_episode(
        "gooaye", episode_id, api_key="fake-key", data_dir=tmp_path
    )

    assert result["episode_id"] == episode_id
    assert result["podcast"] == "gooaye"
    assert result["model"] == "jev-1.13.0"
    assert result["window_seconds"] == 60
    assert "SpaceX" in result["candidates"]
    assert result["topics"] == [
        "SpaceX 與 Cerebras 股票解禁與籌碼流動性",
        "NVIDIA 800V DC 白皮書與伺服器電源架構演進",
        "抄底與市場心理學",
    ]
    assert len(result["windows"]) == 1
    w = result["windows"][0]
    assert w["idx"] == 1
    assert w["start"] == 0.0
    assert w["end"] == 5.0
    assert w["company"] == "SpaceX"
    assert w["company_conf"] == 0.91
    assert w["topic"] == "抄底與市場心理學"
    assert w["topic_conf"] == 0.77
    assert w["view"] == 0.62
    assert w["text"] == "測試視窗文字"
    assert result["usage"] == {"input_tokens": 500, "cost_usd": 500 * 0.042 / 1_000_000}
    assert "indexed_at" in result

    index_path = tmp_path / "index" / f"{episode_id}.json"
    assert index_path.exists()
    on_disk = json.loads(index_path.read_text(encoding="utf-8"))
    assert on_disk == result


def test_index_episode_full_api_failure_raises(tmp_path, monkeypatch):
    episode_id = "EP_TEST"
    _write_episode_fixture(tmp_path, episode_id)

    def failing_post(payload, api_key, timeout=60):
        raise RuntimeError("boom")

    monkeypatch.setattr(jix, "post_request", failing_post)
    monkeypatch.setattr(jix.time, "sleep", lambda s: None)

    with pytest.raises(RuntimeError):
        jix.index_episode("gooaye", episode_id, api_key="fake-key", data_dir=tmp_path)

    assert not (tmp_path / "index" / f"{episode_id}.json").exists()


def test_index_episode_unreadable_transcript_raises(tmp_path):
    # No fixture written at all -> FileNotFoundError, a programming/data
    # error that must propagate (not be swallowed as an API failure).
    with pytest.raises(FileNotFoundError):
        jix.index_episode("gooaye", "EP_MISSING", api_key="fake-key", data_dir=tmp_path)


# ---------------------------------------------------------------------------
# 06_index_jev.py step script — subprocess + dynamic import
#
# The filename starts with a digit, so it can't be `import`ed normally;
# importlib.util loads it by path for in-process monkeypatching.
# ---------------------------------------------------------------------------

def _load_step_module():
    spec = importlib.util.spec_from_file_location("_index_jev_step", STEP_SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_missing_key_prints_warning_and_exits_0(tmp_path):
    env = {**__import__("os").environ, "PODCAST": "gooaye"}
    env.pop("TYPESAFE_API_KEY", None)

    proc = subprocess.run(
        [str(VENV_PYTHON), str(STEP_SCRIPT), "--episodes", "688"],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )

    assert proc.returncode == 0
    assert "WARNING" in proc.stderr
    assert "TYPESAFE_API_KEY" in proc.stderr


def test_per_episode_api_failure_is_skipped_with_warning(tmp_path, monkeypatch, capsys):
    episode_id = "EP9001"
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    _write_episode_fixture(tmp_path / "gooaye", episode_id)
    monkeypatch.setenv("TYPESAFE_API_KEY", "fake-key")
    monkeypatch.setenv("PODCAST", "gooaye")
    monkeypatch.setattr(sys, "argv", ["06_index_jev.py"])

    module = _load_step_module()

    def failing_post(payload, api_key, timeout=60):
        raise RuntimeError("boom")

    monkeypatch.setattr(module.jev_index, "post_request", failing_post)
    monkeypatch.setattr(module.jev_index.time, "sleep", lambda s: None)

    with pytest.raises(SystemExit) as exc:
        module.main()

    assert exc.value.code == 0
    captured = capsys.readouterr()
    assert "WARNING" in captured.err
    assert episode_id in captured.err
    assert not (tmp_path / "gooaye" / "index" / f"{episode_id}.json").exists()
