"""Project-relative paths and optional user overrides for Video Clone.

All defaults are relative to the project root (directory containing app.py).
Cloning the repo onto another machine keeps working without hardcoded drives.

Optional overrides (assets_dir, finals_dir) are stored in work/settings.json:
- Paths under the project are saved relative to ROOT (portable).
- Paths outside the project are saved absolute (machine-specific).
- Missing/invalid cached paths fall back to project defaults.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

# Project root: .../video-clone-mvp  (parent of video_clone package)
ROOT = Path(__file__).resolve().parent.parent

# Defaults — always under ROOT (portable across machines).
ASSETS_DIR = ROOT / "assets"
FACE_FILENAME = "face.jpg"
BG_FILENAME = "background.jpg"

FACE_PATH = ASSETS_DIR / FACE_FILENAME
BG_PATH = ASSETS_DIR / BG_FILENAME

# Accept either .jpg or common alternates when resolving.
FACE_CANDIDATES = ("face.jpg", "face.jpeg", "face.png", "face.webp")
BG_CANDIDATES = (
    "background.jpg",
    "background.jpeg",
    "background.png",
    "background.webp",
    "bg.jpg",
    "bg.png",
)

WORK_ROOT = ROOT / "work"
INBOX_ROOT = WORK_ROOT / "inbox"
DOWNLOADS_ROOT = WORK_ROOT / "downloads"
LATEST_POINTER = WORK_ROOT / "LATEST.json"
SETTINGS_PATH = WORK_ROOT / "settings.json"

# Default finals folder (override via get/set_finals_dir).
FINAL_OUTPUTS_DIR = ROOT / "video_final_outputs"


# ---------------------------------------------------------------------------
# Settings I/O + portable path encoding
# ---------------------------------------------------------------------------


def load_settings() -> dict[str, Any]:
    if not SETTINGS_PATH.is_file():
        return {}
    try:
        data = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def save_settings(settings: dict[str, Any]) -> None:
    WORK_ROOT.mkdir(parents=True, exist_ok=True)
    SETTINGS_PATH.write_text(
        json.dumps(settings, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def path_to_setting(path: str | Path) -> str:
    """
    Encode a path for settings.json.
    Prefer project-relative (portable); keep absolute only when outside ROOT.
    """
    p = Path(path).expanduser().resolve()
    root = ROOT.resolve()
    try:
        rel = p.relative_to(root)
        return rel.as_posix()
    except ValueError:
        return str(p)


def path_from_setting(value: str | Path) -> Path:
    """Decode a settings path (relative → under ROOT, absolute → as-is)."""
    p = Path(str(value)).expanduser()
    if not p.is_absolute():
        p = ROOT / p
    return p.resolve()


def _cached_dir(key: str, default: Path, *, must_exist: bool = True) -> Path:
    """Return cached directory if valid, else default.resolve()."""
    raw = load_settings().get(key)
    if raw:
        try:
            p = path_from_setting(str(raw))
            if (not must_exist) or p.is_dir():
                return p
        except OSError:
            pass
    return default.resolve()


# ---------------------------------------------------------------------------
# Assets dir (face + background)
# ---------------------------------------------------------------------------


def get_assets_dir() -> Path:
    """Active assets folder: cached override if valid, else project `assets/`."""
    return _cached_dir("assets_dir", ASSETS_DIR, must_exist=True)


def set_assets_dir(path: str | Path) -> Path:
    """Validate, cache (portable form), and return the resolved assets directory."""
    p = Path(path).expanduser()
    if not p.is_absolute():
        p = (ROOT / p).resolve()
    else:
        p = p.resolve()
    if not p.is_dir():
        raise NotADirectoryError(f"Assets folder does not exist: {p}")
    settings = load_settings()
    settings["assets_dir"] = path_to_setting(p)
    save_settings(settings)
    return p


def reset_assets_dir() -> Path:
    """Clear cached assets override; fall back to project `assets/`."""
    settings = load_settings()
    settings.pop("assets_dir", None)
    save_settings(settings)
    return ASSETS_DIR.resolve()


# ---------------------------------------------------------------------------
# Finals dir (published videos)
# ---------------------------------------------------------------------------


def get_finals_dir() -> Path:
    """
    Active finals folder: cached override if valid, else project
    `video_final_outputs/`. Creates the default folder on demand when used
    by final_output_path / publish — not here unless override missing.
    """
    return _cached_dir("finals_dir", FINAL_OUTPUTS_DIR, must_exist=True)


def set_finals_dir(path: str | Path, *, create: bool = True) -> Path:
    """Cache finals directory (create if needed). Stored portable when under ROOT."""
    p = Path(path).expanduser()
    if not p.is_absolute():
        p = (ROOT / p).resolve()
    else:
        p = p.resolve()
    if create:
        p.mkdir(parents=True, exist_ok=True)
    if not p.is_dir():
        raise NotADirectoryError(f"Finals folder does not exist: {p}")
    settings = load_settings()
    settings["finals_dir"] = path_to_setting(p)
    save_settings(settings)
    return p


def reset_finals_dir() -> Path:
    """Clear cached finals override; fall back to project `video_final_outputs/`."""
    settings = load_settings()
    settings.pop("finals_dir", None)
    save_settings(settings)
    return FINAL_OUTPUTS_DIR.resolve()


def final_output_path(run_id: str) -> Path:
    """Canonical published path: <finals_dir>/<run_id>.mp4"""
    safe = "".join(
        ch if (ch.isalnum() or ch in "-_") else "_" for ch in (run_id or "run").strip()
    ).strip("._") or "run"
    out_dir = get_finals_dir()
    out_dir.mkdir(parents=True, exist_ok=True)
    return out_dir / f"{safe}.mp4"


def paths_status() -> dict[str, Any]:
    """Snapshot of all key paths for UI / CLI (resolved absolute for display)."""
    assets = get_assets_dir()
    finals = get_finals_dir()
    work = WORK_ROOT.resolve()
    root = ROOT.resolve()
    return {
        "project": str(root),
        "work": str(work),
        "settings": str(SETTINGS_PATH.resolve()),
        "assets_dir": str(assets),
        "assets_is_default": assets == ASSETS_DIR.resolve(),
        "finals_dir": str(finals),
        "finals_is_default": finals == FINAL_OUTPUTS_DIR.resolve(),
        "defaults": {
            "assets_dir": str(ASSETS_DIR.resolve()),
            "finals_dir": str(FINAL_OUTPUTS_DIR.resolve()),
            "work": str(work),
        },
    }


# ---------------------------------------------------------------------------
# Face / background resolution
# ---------------------------------------------------------------------------


def resolve_face(assets_dir: Path | None = None) -> Path:
    base = Path(assets_dir).resolve() if assets_dir is not None else get_assets_dir()
    for name in FACE_CANDIDATES:
        p = base / name
        if p.is_file():
            return p.resolve()
    raise FileNotFoundError(
        f"Fixed face image not found in {base}. "
        f"Put one of {FACE_CANDIDATES} there."
    )


def resolve_bg(assets_dir: Path | None = None) -> Path:
    base = Path(assets_dir).resolve() if assets_dir is not None else get_assets_dir()
    for name in BG_CANDIDATES:
        p = base / name
        if p.is_file():
            return p.resolve()
    raise FileNotFoundError(
        f"Fixed background image not found in {base}. "
        f"Put one of {BG_CANDIDATES} there."
    )


def assets_status(assets_dir: Path | None = None) -> dict:
    base = (
        Path(assets_dir).resolve() if assets_dir is not None else get_assets_dir()
    )
    face = None
    bg = None
    try:
        face = resolve_face(base)
    except FileNotFoundError:
        pass
    try:
        bg = resolve_bg(base)
    except FileNotFoundError:
        pass
    default = ASSETS_DIR.resolve()
    return {
        "assets_dir": str(base),
        "is_default": base == default,
        "face": str(face) if face else None,
        "bg": str(bg) if bg else None,
        "ok": bool(face and bg),
    }
