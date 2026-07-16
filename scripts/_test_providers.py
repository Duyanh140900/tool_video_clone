"""Quick provider smoke test. Pass a TikTok URL as argv[1]."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from video_clone.download import (  # noqa: E402
    download_tiktok_video,
    download_via_snaptik,
    download_via_tikwm,
    probe_has_video,
    resolve_snaptik_video_urls,
    resolve_tikwm_video_url,
)

url = sys.argv[1] if len(sys.argv) > 1 else ""
if not url:
    print("Usage: python scripts/_test_providers.py <tiktok_url>")
    raise SystemExit(2)

out = ROOT / "work" / "downloads" / "_provider_test"
out.mkdir(parents=True, exist_ok=True)

print("== snaptik resolve ==")
try:
    urls = resolve_snaptik_video_urls(url)
    print("urls", len(urls))
    for u in urls[:5]:
        print(" ", u[:120])
except Exception as e:
    print("FAIL", e)

print("== tikwm resolve ==")
try:
    print(resolve_tikwm_video_url(url)[:120])
except Exception as e:
    print("FAIL", e)

print("== full download auto ==")
try:
    p = download_tiktok_video(url, out)
    print("path", p, "has_video", probe_has_video(p), "size", p.stat().st_size)
except Exception as e:
    print("FAIL", e)
