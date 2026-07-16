"""Chain multiple animated clips into one continuous video (no loop)."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from .assemble import probe_duration, _require_ffmpeg


def extract_last_frame(video: Path, out_path: Path) -> Path:
    """Grab near-last frame for continuity into the next image_to_video shot."""
    ffmpeg = _require_ffmpeg()
    video = video.resolve()
    out_path = out_path.resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        ffmpeg,
        "-y",
        "-sseof",
        "-0.05",
        "-i",
        str(video),
        "-frames:v",
        "1",
        "-update",
        "1",
        "-q:v",
        "2",
        str(out_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0 or not out_path.is_file():
        raise RuntimeError(
            "Failed to extract last frame:\n"
            + (result.stderr[-1500:] if result.stderr else result.stdout)
        )
    return out_path


def concat_videos(
    clips: list[Path],
    out_path: Path,
    *,
    width: int = 720,
    height: int = 1280,
    fps: int = 24,
) -> Path:
    """
    Concatenate clips with re-encode so different AI shots join cleanly.
    Video-only output (audio attached later via assemble).
    """
    if len(clips) < 1:
        raise ValueError("Need at least one clip")
    ffmpeg = _require_ffmpeg()
    out_path = out_path.resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    clips = [c.resolve() for c in clips]
    for c in clips:
        if not c.is_file():
            raise FileNotFoundError(f"Clip not found: {c}")

    # filter_complex: scale/pad each, then concat
    inputs: list[str] = []
    filters: list[str] = []
    for i, c in enumerate(clips):
        inputs.extend(["-i", str(c)])
        filters.append(
            f"[{i}:v]scale={width}:{height}:force_original_aspect_ratio=decrease,"
            f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,fps={fps},setsar=1,"
            f"format=yuv420p[v{i}]"
        )
    concat_in = "".join(f"[v{i}]" for i in range(len(clips)))
    filters.append(f"{concat_in}concat=n={len(clips)}:v=1:a=0[v]")
    filter_complex = ";".join(filters)

    cmd = [
        ffmpeg,
        "-y",
        *inputs,
        "-filter_complex",
        filter_complex,
        "-map",
        "[v]",
        "-an",
        "-c:v",
        "libx264",
        "-preset",
        "fast",
        "-crf",
        "18",
        "-pix_fmt",
        "yuv420p",
        str(out_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(
            "ffmpeg concat failed:\n"
            + (result.stderr[-2000:] if result.stderr else result.stdout)
        )
    return out_path


def plan_shot_durations(audio_seconds: float, prefer: int = 6) -> list[int]:
    """
    Split target length into 6s/10s image_to_video chunks.
    Prefer 6s shots; use one 10s tail when remainder is awkward.
    """
    if audio_seconds <= 0:
        raise ValueError("audio_seconds must be positive")
    remaining = audio_seconds
    shots: list[int] = []
    # Fill with 6s while remaining > 10 (leave room for a clean last chunk)
    while remaining > 10.5:
        shots.append(6)
        remaining -= 6
    if remaining <= 0.05:
        return shots or [6]
    if remaining <= 6.5:
        shots.append(6)
    else:
        shots.append(10)
    return shots
