"""Fixed paths and defaults for Video Clone."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

# Project root: .../video-clone-mvp
ROOT = Path(__file__).resolve().parent.parent

# Default assets — put face.jpg + background.jpg here (not uploaded per run).
# User may override via UI; path is cached in work/settings.json.
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

# All finished videos land here, named by run id: <run_id>.mp4
FINAL_OUTPUTS_DIR = ROOT / "video_final_outputs"


def final_output_path(run_id: str) -> Path:
    """Canonical published path: video_final_outputs/<run_id>.mp4"""
    safe = "".join(
        ch if (ch.isalnum() or ch in "-_") else "_" for ch in (run_id or "run").strip()
    ).strip("._") or "run"
    return FINAL_OUTPUTS_DIR / f"{safe}.mp4"


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


def get_assets_dir() -> Path:
    """
    Active assets folder: cached path from settings if it still exists,
    otherwise project default `assets/`.
    """
    cached = load_settings().get("assets_dir")
    if cached:
        p = Path(str(cached)).expanduser()
        try:
            if p.is_dir():
                return p.resolve()
        except OSError:
            pass
    return ASSETS_DIR.resolve()


def set_assets_dir(path: str | Path) -> Path:
    """Validate, cache, and return the resolved assets directory."""
    p = Path(path).expanduser().resolve()
    if not p.is_dir():
        raise NotADirectoryError(f"Assets folder does not exist: {p}")
    settings = load_settings()
    settings["assets_dir"] = str(p)
    save_settings(settings)
    return p


def reset_assets_dir() -> Path:
    """Clear cached override; fall back to project default `assets/`."""
    settings = load_settings()
    settings.pop("assets_dir", None)
    save_settings(settings)
    return ASSETS_DIR.resolve()


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
