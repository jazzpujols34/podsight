"""Tests for ASR term corrections (src/config.apply_term_corrections).

Every fixture below is a real error observed in gooaye EP0688 (2026-08-15).
The "must not touch" cases exist because a bad correction rule silently
corrupts every future transcript - that failure mode is worse than the typo.
"""
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.config import (
    apply_term_corrections, convert_to_traditional, looks_simplified,
    normalize_transcript_text,
)


@pytest.mark.parametrize("wrong,right", [
    # Domain nouns
    ("這些電壓中心會摧毀掉你們的電力", "這些資料中心會摧毀掉你們的電力"),
    ("公立半導體他們也是在這裡面的一環", "功率半導體他們也是在這裡面的一環"),
    ("像是什麼銅牌跟線纜 Connector", "像是什麼銅排跟線纜 Connector"),
    ("然後說更小的一個這個福特數", "然後說更小的一個這個伏特數"),
    ("它所拿到的頭片的數量也是越來越高", "它所拿到的投片的數量也是越來越高"),
    # Finance vocabulary
    ("另外一家最近也有大量的股票結晶要丟出來", "另外一家最近也有大量的股票解禁要丟出來"),
    ("上修這個P1乘數的東西", "上修這個PE 乘數的東西"),
    ("如果他們有開財報或是字節的", "如果他們有開財報或是自結的"),
    ("想要什麼完美抄底完美討頂什麼的", "想要什麼完美抄底完美逃頂什麼的"),
    ("對於這兩個原件的看法", "對於這兩個元件的看法"),
    # Latin-script, case-insensitive
    ("總之Cerebrus這家公司", "總之Cerebras這家公司"),
    ("公布Desecrated Inference架構", "公布Disaggregated Inference架構"),
    ("把它簡單的拆成是Pre-File跟Decode", "把它簡單的拆成是Prefill跟Decode"),
    ("X-RAM我們之前有跟大家討論過", "SRAM我們之前有跟大家討論過"),
    ("或是說什麼那種超大安培數的Bus Doct", "或是說什麼那種超大安培數的Bus Duct"),
    ("就會變成像什麼TRUSST", "就會變成像什麼SST"),
    ("800V再到54V的SHOFT", "800V再到54V的Shelf"),
])
def test_corrects_observed_errors(wrong, right):
    assert apply_term_corrections(wrong) == right


def test_latin_matching_is_case_insensitive():
    assert apply_term_corrections("cerebrus and CEREBRUS") == "Cerebras and Cerebras"


def test_is_idempotent():
    """Backfill may run twice over the same file - it must converge."""
    once = apply_term_corrections("這些電壓中心的Cerebrus股票結晶")
    assert apply_term_corrections(once) == once


@pytest.mark.parametrize("text", [
    # Already-correct text must survive untouched
    "資料中心的功率半導體用了 SiC 跟 GaN",
    "Cerebras 的 Wafer-Scale Engine 主打 Prefill 與 Decode 拆分",
    "被動元件漲價，銅排截面越來越大",
    "800V 降到 54V 之後安培數從 6.1kA 掉到 0.4kA",
])
def test_leaves_correct_text_alone(text):
    assert apply_term_corrections(text) == text


def test_handles_empty_input():
    assert apply_term_corrections("") == ""


def test_longer_keys_win():
    """'電壓Center' must not be half-eaten by a shorter overlapping key."""
    assert apply_term_corrections("現在電壓Center都不用用電是不是") == (
        "現在資料中心都不用用電是不是"
    )


# --- Simplified -> Traditional conversion -----------------------------------

@pytest.mark.parametrize("text,expected", [
    ("这个数据中心", True),
    ("内存软件", True),
    ("峇里島", False),        # already Traditional
    ("歡迎收聽股癌", False),   # already Traditional
    ("到這個峇里島健身房", False),
    ("五公里", False),        # neutral characters only - must not convert
    ("", False),
])
def test_looks_simplified(text, expected):
    assert looks_simplified(text) is expected


def test_converts_real_simplified():
    assert convert_to_traditional("这个数据中心") == "這個資料中心"


@pytest.mark.parametrize("text", [
    # Simplified merged 里/裡/裏, so a blind s2twp turns 峇里島 into 峇裡島.
    # These must survive conversion untouched.
    "峇里島",
    "到這個峇里島健身房",
    "五公里",
    "這裡的資料中心",
])
def test_conversion_never_corrupts_traditional(text):
    assert convert_to_traditional(text) == text


def test_conversion_is_idempotent():
    once = convert_to_traditional("这个数据中心的内存")
    assert convert_to_traditional(once) == once


def test_normalize_handles_a_simplified_segment():
    """Whisper emits one script per segment, so this is the common case."""
    once = normalize_transcript_text("这些电压中心用Cerebrus的X-RAM")
    assert once == "這些資料中心用Cerebras的SRAM"


def test_normalize_handles_a_traditional_segment():
    once = normalize_transcript_text("到這個峇里島健身房,講電壓中心")
    assert once == "到這個峇里島健身房,講資料中心"


@pytest.mark.parametrize("raw", [
    "这些电压中心用Cerebrus的X-RAM",
    "到這個峇里島健身房,講電壓中心",
    "股票結晶要丟出來,P1乘數上修",
    "",
])
def test_normalize_is_idempotent(raw):
    """The backfill re-runs over its own output - it must converge."""
    once = normalize_transcript_text(raw)
    assert normalize_transcript_text(once) == once


def test_mixed_script_segment_is_left_alone():
    """Known, deliberate limitation.

    A segment carrying both scripts is not converted - the gate needs zero
    Traditional-only characters. Measured at 0.15-1.9% of lines across gooaye
    EP0685-0688. Under-converting is recoverable; corrupting 峇里島 -> 峇裡島
    is not. Term corrections still apply to whichever script matches.
    """
    mixed = "这些电压中心到這個峇里島"
    out = normalize_transcript_text(mixed)
    assert "峇里島" in out          # not corrupted
    assert "电压中心" in out         # not converted either - documented gap
