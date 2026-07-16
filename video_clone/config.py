"""Fixed paths and defaults for Video Clone."""

from __future__ import annotations

from pathlib import Path

# Project root: .../video-clone-mvp
ROOT = Path(__file__).resolve().parent.parent

# Fixed assets — put face.jpg + background.jpg here (not uploaded per run).
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

# All finished videos land here, named by run id: <run_id>.mp4
FINAL_OUTPUTS_DIR = ROOT / "video_final_outputs"


def final_output_path(run_id: str) -> Path:
    """Canonical published path: video_final_outputs/<run_id>.mp4"""
    safe = "".join(
        ch if (ch.isalnum() or ch in "-_") else "_" for ch in (run_id or "run").strip()
    ).strip("._") or "run"
    return FINAL_OUTPUTS_DIR / f"{safe}.mp4"


def resolve_face(assets_dir: Path | None = None) -> Path:
    base = assets_dir or ASSETS_DIR
    for name in FACE_CANDIDATES:
        p = base / name
        if p.is_file():
            return p.resolve()
    raise FileNotFoundError(
        f"Fixed face image not found in {base}. "
        f"Put one of {FACE_CANDIDATES} there."
    )


def resolve_bg(assets_dir: Path | None = None) -> Path:
    base = assets_dir or ASSETS_DIR
    for name in BG_CANDIDATES:
        p = base / name
        if p.is_file():
            return p.resolve()
    raise FileNotFoundError(
        f"Fixed background image not found in {base}. "
        f"Put one of {BG_CANDIDATES} there."
    )


def assets_status(assets_dir: Path | None = None) -> dict:
    base = (assets_dir or ASSETS_DIR).resolve()
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
    return {
        "assets_dir": str(base),
        "face": str(face) if face else None,
        "bg": str(bg) if bg else None,
        "ok": bool(face and bg),
    }
