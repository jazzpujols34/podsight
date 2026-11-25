"""Public pages carry the Cloudflare Web Analytics counter; the gated archive does not.

2026-11-25: podsight.tw had no visitor counter at all. The site is on Vercel, so
Cloudflare cannot add its script at the edge: each page template must carry it.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from pipeline.generate_public_site import (  # noqa: E402
    PODCASTS, analytics_for, generate_404_page,
)

GATED = next(pid for pid, cfg in PODCASTS.items() if cfg.get("gated"))
PUBLIC = next(pid for pid, cfg in PODCASTS.items() if not cfg.get("gated"))


def test_public_pages_get_the_counter():
    assert "static.cloudflareinsights.com/beacon.min.js" in analytics_for(PUBLIC)
    assert "static.cloudflareinsights.com/beacon.min.js" in analytics_for()


def test_gated_archive_is_not_counted():
    assert analytics_for(GATED) == ""


def test_a_generated_page_has_exactly_one_counter_inside_head():
    html = generate_404_page()
    head = html.split("</head>")[0]
    assert html.count("cloudflareinsights") == 1
    assert "cloudflareinsights" in head
