"""Topic extraction for the Telegram publisher.

Telegram is the only production-active publisher, so a bad _extract_main_topics
ships straight to the channel. These cases are transcribed from real summaries
across all three shows — the two heading styles diverged enough that a single
regex could not serve both.

Run:  ./venv/bin/python -m unittest discover tests
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.social.formatters.telegram import TelegramFormatter


class ExtractMainTopicsTest(unittest.TestCase):
    def setUp(self):
        self.fmt = TelegramFormatter()

    def extract(self, text):
        return self.fmt._extract_main_topics(text)

    # ---- gooaye: numbered-bold headings, noisy in-body labels ----

    def test_gooaye_numbered_bold_headings(self):
        """`**1. Topic**` wins, and the `*   **MK 認為：**` sub-bullets are ignored."""
        text = (
            "### 主要討論話題\n"
            "\n"
            "**1. 當前盤勢解讀：一個月跌完一整年的「暴力修正」**\n"
            "內文段落。\n"
            "*   **相關標的：** 台積電(2330)、台指期\n"
            "\n"
            "**2. 估值防線崩潰：當 10 倍 P/E 變成無底洞**\n"
            "*   **市場認為：** 績優股跌到 15 倍 P/E 是便宜買點。\n"
            "*   **MK 認為：** 5 倍、3 倍 P/E 都可能出現。\n"
            "\n"
            "### MK 的操作心法與作法\n"
            "*   **部位與槓桿管理：**\n"
        )
        self.assertEqual(
            self.extract(text),
            [
                "當前盤勢解讀：一個月跌完一整年的「暴力修正」",
                "估值防線崩潰：當 10 倍 P/E 變成無底洞",
            ],
        )

    def test_generic_labels_are_not_topics(self):
        """Regression: these used to be emitted as the topic list itself."""
        text = (
            "### 主要討論話題\n"
            "*   **MK 的觀點與推論：** 一段內文。\n"
            "*   **市場認為：** 另一段內文。\n"
            "*   **相關標的：** 台積電(2330)\n"
        )
        self.assertEqual(self.extract(text), [])

    # ---- yutinghao: bullet-bold headings behind a `話題名稱：` label ----

    def test_yutinghao_label_prefix_is_stripped_not_skipped(self):
        """`- **話題名稱：<real topic>**` keeps the topic, drops the label."""
        text = (
            "### 主要討論話題\n"
            "\n"
            "- **話題名稱：台積電權重巨獸與內外資對作**\n"
            "  - **詳細說明：** 台積電單日大漲 85 元。\n"
            "  - **市場影響：** 指數與台積電高度掛鉤。\n"
            "\n"
            "- **話題名稱：AI 營收重塑台積電估值**\n"
            "  - **投資啟示：** 關注 2026 年資本支出。\n"
            "\n"
            "---\n"
        )
        self.assertEqual(
            self.extract(text),
            ["台積電權重巨獸與內外資對作", "AI 營收重塑台積電估值"],
        )

    def test_bare_label_with_no_name_is_dropped(self):
        """gooaye writes `**話題名稱：**` with the name outside the bold — nothing to keep."""
        text = "### 主要討論話題\n*   **話題名稱：** 這裡才是名字\n"
        self.assertEqual(self.extract(text), [])

    # ---- shared behaviour ----

    def test_ordinal_prefixes_are_stripped(self):
        text = (
            "### 主要討論話題\n"
            "1. **1. 第一個話題**\n"
            "2. **2、第二個話題**\n"
        )
        self.assertEqual(self.extract(text), ["第一個話題", "第二個話題"])

    def test_section_boundary_is_respected(self):
        """Headings after the section end must not leak in."""
        text = (
            "### 主要討論話題\n"
            "- **真的話題**\n"
            "### 提到的股票/ETF/標的\n"
            "- **台積電 (2330)**\n"
        )
        self.assertEqual(self.extract(text), ["真的話題"])

    def test_substring_match_does_not_eat_real_topics(self):
        """「操作邏輯」 is an exact-match label, so a topic containing it survives."""
        text = "### 主要討論話題\n- **殺人心盤的操作邏輯**\n"
        self.assertEqual(self.extract(text), ["殺人心盤的操作邏輯"])

    def test_missing_section_returns_empty(self):
        self.assertEqual(self.extract("### 一句話總結\n沒有話題區塊。\n"), [])


class MarkdownHeadingTopicsTest(unittest.TestCase):
    """"#### Topic Name" headings — the third style, added 2026-08-21.

    Summaries began titling topics with markdown sub-headings instead of bold
    text. Two things broke at once: _get_topics_section ended the section at the
    first "####" (because "####".startswith("###")), and no tier recognised the
    heading. Ten episodes — including 2026-08-21, whose Telegram post went out
    with no 主要討論話題 block at all — extracted zero topics.
    """

    def setUp(self):
        self.fmt = TelegramFormatter()

    NUMBERED = """### 主要討論話題

#### 1. 美國債務危機與「勒索式」寬鬆
- **詳細說明**：美國國債突破 40 兆美元。
- **市場影響與投資啟示**：投資人要求更高的風險補償。

#### 2. AI 時代的政治悖論與民意反彈
- **詳細說明**：多數美國民眾對資料中心擴建存有疑慮。

---

### 財經觀點與分析
- 之後的段落不該被當成話題。
"""

    UNNUMBERED = """### 主要討論話題

#### 美國高利率與科技巨頭舉債疑慮
- **詳細說明**：公債殖利率攀升對舉債擴張形成壓力。

#### 盤面主流與低本益比 IC 設計抗跌表現
- **詳細說明**：資金轉向低本益比族群。
"""

    def test_numbered_headings_all_extracted(self):
        got = self.fmt._extract_main_topics(self.NUMBERED)
        self.assertEqual(len(got), 2, got)
        self.assertTrue(got[0].startswith("美國債務危機"), got)

    def test_field_labels_are_not_topics(self):
        got = self.fmt._extract_main_topics(self.NUMBERED)
        self.assertNotIn("詳細說明", got)
        self.assertNotIn("市場影響與投資啟示", got)

    def test_section_ends_at_the_next_real_heading(self):
        got = self.fmt._extract_main_topics(self.NUMBERED)
        self.assertFalse(any("財經觀點" in g for g in got), got)

    def test_unnumbered_headings_extracted(self):
        """zhaohua/gooaye emit '#### Name' with no number."""
        got = self.fmt._extract_main_topics(self.UNNUMBERED)
        self.assertEqual(len(got), 2, got)
        self.assertTrue(got[1].startswith("盤面主流"), got)


class CorpusGuardTest(unittest.TestCase):
    """Every real summary on disk must yield at least one topic.

    The pre-fix extractor returned nothing for 59 of 356 episodes — those
    Telegram posts shipped with an empty topic list. This is the guard that
    keeps that from coming back.
    """

    def test_no_episode_extracts_zero_topics(self):
        root = Path(__file__).resolve().parent.parent / "data"
        fmt = TelegramFormatter()
        empty, scanned = [], 0
        for show in ("gooaye", "yutinghao", "zhaohua"):
            d = root / show / "summaries"
            if not d.exists():
                continue
            for f in sorted(d.glob("*")):
                if not f.is_file():
                    continue
                scanned += 1
                text = f.read_text(encoding="utf-8", errors="replace")
                if "主要討論話題" not in text:
                    continue  # a few episodes genuinely have no topics section
                if not fmt._extract_main_topics(text):
                    empty.append(f"{show}/{f.name}")
        if scanned == 0:
            self.skipTest("no summary corpus checked out")
        self.assertEqual(empty, [], f"{len(empty)} of {scanned} episodes extracted no topics")


if __name__ == "__main__":
    unittest.main(verbosity=2)
