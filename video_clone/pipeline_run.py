"""Shared prepare pipeline used by CLI and Streamlit UI."""

from __future__ import annotations

import json
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any

from .assemble import mux_audio, probe_duration
from .chain import concat_videos, plan_shot_durations
from .compose import compose_hero
from .config import (
    DOWNLOADS_ROOT,
    FINAL_OUTPUTS_DIR,
    INBOX_ROOT,
    LATEST_POINTER,
    WORK_ROOT,
    final_output_path,
    get_assets_dir,
    resolve_bg,
    resolve_face,
)
from .download import download_tiktok_video, is_tiktok_url, normalize_url
from .extract import extract_assets
from .style import (
    DEFAULT_STYLE_ID,
    DEFAULT_STYLE_NAME,
    build_shot_plan,
    write_prompt_bundle,
)

ROOT = Path(__file__).resolve().parent.parent


def new_run_id(prefix: str = "run") -> str:
    return f"{prefix}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"


def prepare_run(
    *,
    video: Path,
    face: Path | None = None,
    bg: Path | None = None,
    out_dir: Path | None = None,
    run_id: str | None = None,
    at: float | None = None,
    skip_face: bool = False,
    skip_bg: bool = False,
    source_url: str | None = None,
) -> dict[str, Any]:
    """
    extract → compose (fixed face/bg by default) → TikTok prompt pack.
    Writes work/<run_id>/ and updates work/LATEST.json for Grok handoff.
    """
    face = Path(face) if face else resolve_face()
    bg = Path(bg) if bg else resolve_bg()
    used_assets_dir = face.parent.resolve()

    rid = run_id or new_run_id()
    out = (out_dir or (WORK_ROOT / rid)).resolve()
    out.mkdir(parents=True, exist_ok=True)
    shots_dir = out / "shots"
    shots_dir.mkdir(exist_ok=True)

    meta = extract_assets(Path(video), out, at=at)
    audio_dur = float(meta["duration"])
    durations = plan_shot_durations(audio_dur)

    hero = out / "hero.jpg"
    compose_hero(
        Path(meta["frame"]),
        face,
        bg,
        hero,
        skip_face=skip_face,
        skip_bg=skip_bg,
    )

    shot_plan = build_shot_plan(durations, hero_name="hero_refined.jpg")
    prompt_paths = write_prompt_bundle(out, shot_plan, audio_seconds=audio_dur)

    # Copy inputs into run for reproducibility
    inputs_dir = out / "inputs"
    inputs_dir.mkdir(exist_ok=True)
    for label, src in (("video", video), ("face", face), ("bg", bg)):
        src = Path(src)
        dest = inputs_dir / f"{label}{src.suffix.lower() or ''}"
        if src.resolve() != dest.resolve():
            shutil.copy2(src, dest)

    if source_url:
        (inputs_dir / "source_url.txt").write_text(
            source_url.strip() + "\n", encoding="utf-8"
        )

    handoff = {
        "run_id": rid,
        "style_id": DEFAULT_STYLE_ID,
        "style_name": DEFAULT_STYLE_NAME,
        "source_url": source_url,
        "out_dir": str(out),
        "frame": str(meta["frame"]),
        "audio": str(meta["audio"]),
        "hero": str(hero),
        "hero_refined": str(out / "hero_refined.jpg"),
        "face": str(face),
        "bg": str(bg),
        "assets_dir": str(used_assets_dir),
        "prompts_md": str(prompt_paths["md"]),
        "prompts_json": str(prompt_paths["json"]),
        "shots_dir": str(shots_dir),
        "audio_seconds": audio_dur,
        "shot_durations": durations,
        "status": "ready_for_grok_animate",
        "grok_message": (
            f"Làm tiếp video-clone run `{rid}`: refine hero + multi-shot TikTok "
            f"animate theo `{prompt_paths['md'].name}`, concat, assemble full audio. "
            f"Thư mục: {out}"
            + (f" | source: {source_url}" if source_url else "")
        ),
        "created_at": datetime.now().isoformat(timespec="seconds"),
    }

    handoff_path = out / "HANDOFF.json"
    handoff_path.write_text(
        json.dumps(handoff, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    WORK_ROOT.mkdir(parents=True, exist_ok=True)
    LATEST_POINTER.write_text(
        json.dumps(handoff, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    (out / "GROK.txt").write_text(handoff["grok_message"] + "\n", encoding="utf-8")

    return {
        **handoff,
        "handoff_path": str(handoff_path),
        "latest_path": str(LATEST_POINTER),
        "meta": {
            "duration": meta["duration"],
            "timestamp": meta["timestamp"],
        },
    }


def prepare_from_tiktok_url(
    url: str,
    *,
    run_id: str | None = None,
    out_dir: Path | None = None,
    at: float | None = None,
    skip_face: bool = False,
    skip_bg: bool = False,
    assets_dir: Path | None = None,
) -> dict[str, Any]:
    """
    Download TikTok URL → use fixed face/bg from assets → prepare_run.
    """
    url = normalize_url(url)
    if not is_tiktok_url(url):
        raise ValueError(f"Not a TikTok URL: {url}")

    assets = Path(assets_dir).resolve() if assets_dir is not None else get_assets_dir()
    face = resolve_face(assets)
    bg = resolve_bg(assets)

    rid = run_id or new_run_id()
    dl_dir = DOWNLOADS_ROOT / rid
    video = download_tiktok_video(url, dl_dir)

    return prepare_run(
        video=video,
        face=face,
        bg=bg,
        out_dir=out_dir or (WORK_ROOT / rid),
        run_id=rid,
        at=at,
        skip_face=skip_face,
        skip_bg=skip_bg,
        source_url=url,
    )


def finish_run(
    *,
    run_dir: Path,
    chain_or_clips: Path | list[Path],
    out_name: str = "final.mp4",
    run_id: str | None = None,
) -> dict[str, Any]:
    run_dir = Path(run_dir).resolve()
    audio = run_dir / "audio.m4a"
    if not audio.is_file():
        raise FileNotFoundError(f"Missing audio: {audio}")

    rid = run_id or run_dir.name

    if isinstance(chain_or_clips, list):
        chain = run_dir / "chain.mp4"
        concat_videos(chain_or_clips, chain)
    else:
        chain = Path(chain_or_clips)

    # Always write work/<run>/final.mp4, then publish to video_final_outputs/<run>.mp4
    final_in_run = run_dir / out_name
    mux_audio(
        chain,
        audio,
        final_in_run,
        mode="trim_to_audio",
        run_id=rid,
        publish=True,
    )
    published = final_output_path(rid)
    # Prefer published path if copy succeeded
    final_path = published if published.is_file() else final_in_run
    return {
        "chain": str(chain),
        "final": str(final_in_run),
        "published": str(final_path),
        "final_outputs_dir": str(FINAL_OUTPUTS_DIR),
        "run_id": rid,
        "duration": probe_duration(final_in_run),
    }


def read_latest() -> dict[str, Any] | None:
    if not LATEST_POINTER.is_file():
        return None
    return json.loads(LATEST_POINTER.read_text(encoding="utf-8"))
