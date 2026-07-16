import re
from pathlib import Path

import requests

s = requests.Session()
s.headers.update(
    {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/122.0.0.0 Safari/537.36"
        ),
        "Accept-Language": "en-US,en;q=0.9",
    }
)
home = s.get("https://snaptik.app/en2", timeout=30)
print("home", home.status_code)
token_m = re.search(r'name="token" value="([^"]+)"', home.text)
print("token", token_m.group(1) if token_m else None)
scripts = re.findall(r'src="(/[^"]+\.js)"', home.text)
print("scripts", scripts[:30])
inline = re.findall(r"<script[^>]*>([\s\S]*?)</script>", home.text)
for i, block in enumerate(inline):
    if "search" in block or "token" in block or "ajax" in block.lower():
        print("inline", i, "len", len(block))
        print(block[:1500])
        print("---")

# Try GET /search with a dummy and see response shape
if token_m:
    r = s.get(
        "https://snaptik.app/search",
        params={
            "url": "https://www.tiktok.com/@tiktok/video/7000000000000000000",
            "lang": "en2",
            "token": token_m.group(1),
        },
        timeout=30,
        headers={"Referer": "https://snaptik.app/en2", "X-Requested-With": "XMLHttpRequest"},
    )
    print("search status", r.status_code, "ctype", r.headers.get("content-type"))
    print(r.text[:2000])
    Path("work/_snaptik_search.html").write_text(r.text, encoding="utf-8")
