"""Topic parsing must not lose topics to sub-headings or bullet style.

2026-08-21: podsight.tw/yutinghao/2026-08-21/ rendered a single topic called
"詳細說明" while the summary file held three properly-titled ones. Two causes:

  1. every section regex ended at (?=\\n---|\\n###), and "\\n###" also matches
     "\\n####", so the 主要討論話題 section was truncated at its first
     "#### 1." sub-heading — topics 2 and 3 never reached the parser;
  2. the surviving fragment then fell through to a later format that picked up
     the "**詳細說明**" label as the topic TITLE.

Separately, the bullet format only accepted "*" bullets, so summaries written
with "-" bullets collapsed into one topic.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from pipeline.generate_public_site import parse_summary  # noqa: E402

H4 = """### 一句話總結
測試摘要。

---

### 主要討論話題

#### 1. 美國債務危機與「勒索式」寬鬆
- **詳細說明**：美國國債突破 40 兆美元，聯邦財政赤字維持在 GDP 6%。
- **市場影響與投資啟示**：投資人要求更高的風險補償。

#### 2. AI 時代的政治悖論與民意反彈
- **詳細說明**：多數美國民眾對資料中心擴建存有疑慮，逾 15 州擬限制。
- **市場影響與投資啟示**：資料中心建置進度可能因民意壓力放緩。

#### 3. 中國 AI 模型的「後發優勢」與價格戰
- **詳細說明**：中國 AI 模型透過開源與極低成本快速進逼美國。
- **市場影響與投資啟示**：競爭從技術轉為價格與規模。

---

### 財經觀點與分析
- **市場對美債政策的反應**：小規模回購無法扭轉美債的上行軌道。

---

### 冷笑話 / 幽默金句
- 測試。
"""

DASH = """### 主要討論話題

- **美伊談判僵局與油價、債市壓力**
  美伊 60 天談判大限到期但條件未到位，布蘭特原油突破 90 美元。

- **美國 AI 資料中心擴建與融資挑戰**
  科技巨頭砸重金興建資料中心，但保險公司因風險過高不願承保。

- **台灣 AI 出口暴賺與超額儲蓄氾濫**
  台灣上市櫃公司第二季稅後淨利突破 2 兆元，主因 AI 伺服器需求。

---
"""


def test_h4_subheadings_do_not_truncate_the_section():
    topics = parse_summary(H4)["topics"]
    assert len(topics) == 3, f"expected 3 topics, got {[t['title'] for t in topics]}"


def test_h4_titles_are_the_topic_names_not_the_field_labels():
    titles = [t["title"] for t in parse_summary(H4)["topics"]]
    assert "詳細說明" not in titles
    assert titles[0].startswith("美國債務危機")
    assert titles[1].startswith("AI 時代的政治悖論")


def test_h4_topic_body_survives():
    first = parse_summary(H4)["topics"][0]["content"]
    assert "40 兆美元" in first


def test_a_following_h3_section_still_parses():
    """The lookahead fix must not swallow the next real ### section.

    NOTE: the fixture keeps a trailing "---" because every section regex here
    ends at (?=\n---|\n###(?!#)) with no end-of-string alternative, so a file's
    LAST section parses as empty. Pre-existing, unrelated to this fix, and left
    alone deliberately — worth its own change.
    """
    assert parse_summary(H4)["strategies"]


def test_dash_bullets_are_split_into_separate_topics():
    topics = parse_summary(DASH)["topics"]
    assert len(topics) == 3, f"expected 3 topics, got {[t['title'] for t in topics]}"
    assert topics[2]["title"].startswith("台灣 AI 出口暴賺")
