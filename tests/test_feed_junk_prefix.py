"""Publisher file-naming prefixes must not blank an episode's date.

2026-08-21: the yutinghao feed delivered
    "2026-08-20 08-31-2026/8/20(四)貝森特護盤!..."
— their SoundCloud filename glued to the front of the real title. Every date
matcher is anchored with re.match, so the prefix made get_episode_id() return
None, podsight.tw/yutinghao/2026-08-20/ was never generated (404), and the
Telegram push aborted with exit 1.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from pipeline.generate_public_site import (  # noqa: E402
    get_episode_id, get_episode_title, get_sort_key, strip_feed_junk_prefix,
)

BROKEN = "2026-08-20 08-31-2026_8_20_四_貝森特護盤_美債有救了_巨頭燒錢換市佔 利_summary.txt"
CLEAN = "2026_8_21_五_巨頭搶錢 誰來接美債_AI是革命or下一場債務危機__早晨財經速解讀__summary.txt"


def test_broken_filename_still_yields_its_date():
    assert get_episode_id(BROKEN, "yutinghao") == "2026-08-20"


def test_clean_filename_is_unchanged():
    assert get_episode_id(CLEAN, "yutinghao") == "2026-08-21"


def test_strip_only_removes_the_publisher_prefix():
    assert strip_feed_junk_prefix(BROKEN).startswith("2026_8_20_")
    assert strip_feed_junk_prefix(CLEAN) == CLEAN


def test_a_date_later_in_the_title_is_not_mistaken_for_the_episode_date():
    """Why we strip rather than switch to re.search."""
    assert get_episode_id("美股展望_2026_1_1_回顧_summary.txt", "yutinghao") is None


def test_broken_filename_sorts_by_its_real_date():
    assert get_sort_key(BROKEN, "yutinghao") == (0, 2026, 8, 20)


def test_title_extraction_survives_the_prefix():
    title = get_episode_title(BROKEN, "yutinghao")
    assert title and "貝森特護盤" in title
