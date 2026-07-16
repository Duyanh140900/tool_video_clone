"""Download dance videos from TikTok via SnapTik (primary) + TikWM / yt-dlp fallbacks."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path
from urllib.parse import unquote, urlparse

import requests
from bs4 import BeautifulSoup

from .snaptik_decoder import decode_snaptik_payload

_TIKTOK_HOSTS = (
    "tiktok.com",
    "www.tiktok.com",
    "vm.tiktok.com",
    "vt.tiktok.com",
    "m.tiktok.com",
)

_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/122.0.0.0 Safari/537.36"
)

# Prefer SnapTik (user request). Fallbacks if SnapTik breaks.
DEFAULT_PROVIDER_ORDER = ("snaptik", "tikwm", "ytdlp")


def is_tiktok_url(url: str) -> bool:
    raw = (url or "").strip()
    if not raw:
        return False
    if not re.match(r"^https?://", raw, re.I):
        raw = "https://" + raw
    try:
        host = urlparse(raw).netloc.lower()
    except Exception:
        return False
    host = host.removeprefix("www.")
    return host.endswith("tiktok.com")


def normalize_url(url: str) -> str:
    raw = (url or "").strip()
    if not raw:
        raise ValueError("Empty URL")
    if not re.match(r"^https?://", raw, re.I):
        raw = "https://" + raw
    return raw


def _session() -> requests.Session:
    s = requests.Session()
    s.headers.update(
        {
            "User-Agent": _UA,
            "Accept": "*/*",
            "Accept-Language": "en-US,en;q=0.9,vi;q=0.8",
        }
    )
    return s


def _require_ffmpeg() -> str:
    exe = shutil.which("ffmpeg")
    if not exe:
        raise RuntimeError("ffmpeg not found on PATH")
    return exe


def _require_ffprobe() -> str:
    exe = shutil.which("ffprobe")
    if not exe:
        raise RuntimeError("ffprobe not found on PATH")
    return exe


def probe_has_video(path: Path) -> bool:
    ffprobe = _require_ffprobe()
    cmd = [
        ffprobe,
        "-v",
        "error",
        "-select_streams",
        "v:0",
        "-show_entries",
        "stream=codec_type",
        "-of",
        "json",
        str(path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        return False
    try:
        data = json.loads(result.stdout or "{}")
    except json.JSONDecodeError:
        return False
    return any(s.get("codec_type") == "video" for s in (data.get("streams") or []))


def _looks_like_video_bytes(data: bytes) -> bool:
    if len(data) < 12:
        return False
    # MP4 often starts with ....ftyp
    if data[4:8] == b"ftyp":
        return True
    # WebM / Matroska
    if data[:4] == b"\x1a\x45\xdf\xa3":
        return True
    # Some CDNs start with mdat later; reject pure ID3/mp3
    if data[:3] == b"ID3" or data[:2] == b"\xff\xfb":
        return False
    return len(data) > 200_000  # large enough to maybe be video


def _download_url_to_file(url: str, dest: Path, *, session: requests.Session | None = None) -> Path:
    s = session or _session()
    dest.parent.mkdir(parents=True, exist_ok=True)
    with s.get(url, stream=True, timeout=120, allow_redirects=True) as r:
        r.raise_for_status()
        ctype = (r.headers.get("content-type") or "").lower()
        if "audio" in ctype and "video" not in ctype:
            raise RuntimeError(f"URL returned audio-only content-type: {ctype}")
        with dest.open("wb") as f:
            for chunk in r.iter_content(chunk_size=1024 * 256):
                if chunk:
                    f.write(chunk)
    if not dest.is_file() or dest.stat().st_size < 10_000:
        raise RuntimeError(f"Downloaded file too small: {dest}")
    return dest


def _to_source_mp4(video: Path, out_dir: Path) -> Path:
    final = out_dir / "source.mp4"
    if video.resolve() == final.resolve() and probe_has_video(final):
        return final

    ffmpeg = _require_ffmpeg()
    cmd = [
        ffmpeg,
        "-y",
        "-i",
        str(video),
        "-map",
        "0:v:0",
        "-map",
        "0:a?",
        "-c:v",
        "libx264",
        "-preset",
        "fast",
        "-crf",
        "18",
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
        "-b:a",
        "192k",
        "-movflags",
        "+faststart",
        str(final),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0 or not final.is_file() or final.stat().st_size == 0:
        err = (result.stderr or result.stdout or "")[-1500:]
        raise RuntimeError(f"Failed to encode to source.mp4:\n{err}")
    if not probe_has_video(final):
        raise RuntimeError("Remuxed file has no video stream")
    return final


# ---------------------------------------------------------------------------
# SnapTik
# ---------------------------------------------------------------------------


def _snaptik_get_token(session: requests.Session) -> str:
    for path in ("/en2", "/en", "/"):
        r = session.get(f"https://snaptik.app{path}", timeout=30)
        r.raise_for_status()
        m = re.search(r'name="token"\s+value="([^"]+)"', r.text)
        if m:
            return m.group(1)
    raise RuntimeError("Could not get SnapTik token from homepage")


def _snaptik_hd_link(session: requests.Session, token_hd: str, base: str) -> str | None:
    try:
        r = session.get(
            f"{base.rstrip('/')}/getHdLink.php",
            params={"token": token_hd},
            timeout=30,
        )
        data = r.json()
        if data.get("url"):
            return str(data["url"])
        if data.get("error"):
            return None
    except Exception:
        return None
    return None


def _snaptik_extract_urls(
    html: str,
    base: str = "https://snaptik.app",
    *,
    session: requests.Session | None = None,
) -> list[str]:
    urls: list[str] = []
    soup = BeautifulSoup(html, "html.parser")
    s = session or _session()

    for a in soup.select("div.video-links a[href], a[href]"):
        href = (a.get("href") or "").strip()
        if not href or href in {"#", "/", "javascript:void(0)"}:
            continue
        if href.startswith("/"):
            href = base + href
        if href.startswith("http"):
            urls.append(href)

    for btn in soup.select(
        "button[data-backup], button[data-tokenhd], button[data-token], a[data-backup]"
    ):
        token_hd = (btn.get("data-tokenhd") or "").strip()
        if token_hd:
            hd = _snaptik_hd_link(s, token_hd, base)
            if hd:
                urls.insert(0, hd)  # prefer HD
        for key in ("data-backup", "data-href"):
            val = (btn.get(key) or "").strip()
            if val.startswith("http"):
                urls.append(val)
            elif val.startswith("/"):
                urls.append(base + val)

    # Regex fallbacks inside decoded payload
    for pat in (
        r'https?://snapxcdn[^"\'\s\\]+',
        r'https?://[^"\'\s\\]+?\.(?:mp4|m3u8)[^"\'\s\\]*',
        r'https?://[^"\'\s\\]*tiktokcdn[^"\'\s\\]+',
        r'(/file\.php\?[^"\']+)',
        r'(https?://snaptik\.app/file\.php\?[^"\']+)',
    ):
        for m in re.findall(pat, html, flags=re.I):
            u = m if m.startswith("http") else base + m
            u = u.replace("\\/", "/").replace("\\u0026", "&")
            urls.append(unquote(u))

    # Dedup preserve order; prefer non-mp3
    seen: set[str] = set()
    ordered: list[str] = []
    for u in urls:
        if u in seen:
            continue
        if any(x in u.lower() for x in (".mp3", "audio", "music")):
            continue
        seen.add(u)
        ordered.append(u)
    return ordered


def resolve_snaptik_video_urls(tiktok_url: str) -> list[str]:
    """Call SnapTik abc2.php and return candidate direct download URLs."""
    tiktok_url = normalize_url(tiktok_url)
    s = _session()
    s.headers.update(
        {
            "Origin": "https://snaptik.app",
            "Referer": "https://snaptik.app/en2",
        }
    )
    token = _snaptik_get_token(s)

    # POST form (current) and GET params (legacy) — try both.
    errors: list[str] = []
    payloads = []

    try:
        r = s.post(
            "https://snaptik.app/abc2.php",
            data={"url": tiktok_url, "token": token, "lang": "en2"},
            timeout=45,
        )
        payloads.append(("POST abc2", r.text))
    except Exception as exc:  # noqa: BLE001
        errors.append(f"POST abc2: {exc}")

    try:
        r = s.get(
            "https://snaptik.app/abc2.php",
            params={"url": tiktok_url, "token": token, "lang": "en2"},
            timeout=45,
        )
        payloads.append(("GET abc2", r.text))
    except Exception as exc:  # noqa: BLE001
        errors.append(f"GET abc2: {exc}")

    # Also try dev.snaptik.app like snaptik-app-api
    try:
        r = s.get("https://dev.snaptik.app/", timeout=30)
        m = re.search(r'name="token"\s+value="([^"]+)"', r.text)
        if m:
            token2 = m.group(1)
            r = s.post(
                "https://dev.snaptik.app/abc2.php",
                data={"url": tiktok_url, "token": token2, "lang": "en"},
                timeout=45,
            )
            payloads.append(("POST dev.abc2", r.text))
    except Exception as exc:  # noqa: BLE001
        errors.append(f"dev.snaptik: {exc}")

    all_urls: list[str] = []
    for label, text in payloads:
        if not text or "error_api_web" in text or text.strip().startswith("Error:"):
            errors.append(f"{label}: error response ({text[:200]!r})")
            continue
        # Plain HTML (no obfuscation)
        if "<a" in text and ("video-links" in text or "download" in text.lower()):
            all_urls.extend(_snaptik_extract_urls(text, session=s))
        # Obfuscated JS payload
        try:
            decoded = decode_snaptik_payload(text)
            all_urls.extend(_snaptik_extract_urls(decoded, session=s))
            # raw links inside decoded js
            all_urls.extend(
                re.findall(r'https?://[^"\'\\]+?\.(?:mp4)[^"\'\\]*', decoded, flags=re.I)
            )
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{label}: decode failed: {exc}")
            # still try regex on raw text
            all_urls.extend(_snaptik_extract_urls(text, session=s))

    # Clean
    cleaned: list[str] = []
    seen: set[str] = set()
    for u in all_urls:
        u = u.replace("\\/", "/").strip()
        if not u.startswith("http"):
            continue
        if u in seen:
            continue
        seen.add(u)
        cleaned.append(u)

    if not cleaned:
        raise RuntimeError(
            "SnapTik did not return a video URL.\n" + "\n".join(errors[-6:])
        )
    return cleaned


def download_via_snaptik(tiktok_url: str, out_dir: Path) -> Path:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    urls = resolve_snaptik_video_urls(tiktok_url)
    s = _session()
    s.headers["Referer"] = "https://snaptik.app/"
    last_err = ""
    for i, url in enumerate(urls[:8]):
        raw = out_dir / f"snaptik_raw_{i}.mp4"
        try:
            _download_url_to_file(url, raw, session=s)
            head = raw.read_bytes()[:64]
            if head.lstrip().startswith(b"<") or head.lstrip().startswith(b"{"):
                last_err = f"URL {i} returned non-media content"
                raw.unlink(missing_ok=True)
                continue
            return _to_source_mp4(raw, out_dir)
        except Exception as exc:  # noqa: BLE001
            last_err = str(exc)
            continue
    raise RuntimeError(
        f"SnapTik returned {len(urls)} URL(s) but download/remux failed: {last_err}"
    )


# ---------------------------------------------------------------------------
# TikWM fallback (clean JSON API)
# ---------------------------------------------------------------------------


def resolve_tikwm_video_url(tiktok_url: str) -> str:
    s = _session()
    r = s.post(
        "https://www.tikwm.com/api/",
        data={"url": normalize_url(tiktok_url), "hd": "1"},
        timeout=45,
        headers={"Referer": "https://www.tikwm.com/"},
    )
    r.raise_for_status()
    data = r.json()
    if data.get("code") not in (0, "0", None) and data.get("msg") not in (None, "success"):
        # tikwm uses code 0 for ok
        if data.get("code") != 0:
            raise RuntimeError(f"TikWM error: {data}")
    payload = data.get("data") or {}
    for key in ("hdplay", "play", "wmplay"):
        url = payload.get(key)
        if url and isinstance(url, str) and url.startswith("http"):
            return url
    raise RuntimeError(f"TikWM returned no play URL: {data}")


def download_via_tikwm(tiktok_url: str, out_dir: Path) -> Path:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    url = resolve_tikwm_video_url(tiktok_url)
    raw = out_dir / "tikwm_raw.mp4"
    _download_url_to_file(url, raw)
    return _to_source_mp4(raw, out_dir)


# ---------------------------------------------------------------------------
# yt-dlp last resort
# ---------------------------------------------------------------------------


def download_via_ytdlp(tiktok_url: str, out_dir: Path) -> Path:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_tmpl = str(out_dir / "ytdlp.%(ext)s")
    cmd = [
        sys.executable,
        "-m",
        "yt_dlp",
        "--no-playlist",
        "--force-overwrites",
        "-f",
        "bv*+ba/b",
        "--merge-output-format",
        "mp4",
        "-o",
        out_tmpl,
        normalize_url(tiktok_url),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError((result.stderr or result.stdout or "")[-1500:])
    candidates = sorted(out_dir.glob("ytdlp.*"), key=lambda p: p.stat().st_mtime, reverse=True)
    candidates = [p for p in candidates if p.suffix.lower() not in {".part", ".ytdl"}]
    if not candidates:
        raise RuntimeError("yt-dlp produced no file")
    if not probe_has_video(candidates[0]):
        raise RuntimeError("yt-dlp produced audio-only file")
    return _to_source_mp4(candidates[0], out_dir)


# ---------------------------------------------------------------------------
# Public entry
# ---------------------------------------------------------------------------


def download_tiktok_video(
    url: str,
    out_dir: Path,
    *,
    providers: tuple[str, ...] = DEFAULT_PROVIDER_ORDER,
) -> Path:
    """
    Download TikTok **video** into out_dir/source.mp4.

    Provider order default: snaptik → tikwm → ytdlp.
    """
    url = normalize_url(url)
    if not is_tiktok_url(url):
        raise ValueError(
            f"Not a TikTok URL: {url}. "
            "Use https://www.tiktok.com/@user/video/... or vm.tiktok.com/..."
        )

    out_dir = Path(out_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    # Clean previous source.*
    for old in out_dir.glob("source.*"):
        try:
            old.unlink()
        except OSError:
            pass

    errors: list[str] = []
    for name in providers:
        try:
            if name == "snaptik":
                path = download_via_snaptik(url, out_dir)
            elif name == "tikwm":
                path = download_via_tikwm(url, out_dir)
            elif name == "ytdlp":
                path = download_via_ytdlp(url, out_dir)
            else:
                continue
            if probe_has_video(path):
                # Write provider used
                (out_dir / "download_meta.json").write_text(
                    json.dumps(
                        {
                            "url": url,
                            "provider": name,
                            "path": str(path),
                            "ts": time.time(),
                        },
                        indent=2,
                    ),
                    encoding="utf-8",
                )
                return path
            errors.append(f"{name}: no video stream in {path}")
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{name}: {exc}")

    raise RuntimeError(
        "Failed to download TikTok video with all providers "
        f"({', '.join(providers)}).\n" + "\n---\n".join(errors)
    )
