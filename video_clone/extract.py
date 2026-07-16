"""Extract a still frame and audio track from the source dance video."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path


def _require_ffmpeg() -> str:
    exe = shutil.which("ffmpeg")
    if not exe:
        raise RuntimeError(
            "ffmpeg not found on PATH. Install FFmpeg and restart the terminal."
        )
    return exe


def _require_ffprobe() -> str:
    exe = shutil.which("ffprobe")
    if not exe:
        raise RuntimeError(
            "ffprobe not found on PATH. Install full FFmpeg build (includes ffprobe)."
        )
    return exe


def probe_media(video: Path) -> dict:
    ffprobe = _require_ffprobe()
    cmd = [
        ffprobe,
        "-v",
        "error",
        "-show_entries",
        "format=duration:stream=index,codec_type,codec_name,width,height",
        "-of",
        "json",
        str(video),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(
            f"ffprobe failed for {video}:\n{(result.stderr or result.stdout)[-1500:]}"
        )
    data = json.loads(result.stdout or "{}")
    streams = data.get("streams") or []
    has_video = any(s.get("codec_type") == "video" for s in streams)
    has_audio = any(s.get("codec_type") == "audio" for s in streams)
    duration = float((data.get("format") or {}).get("duration") or 0.0)
    return {
        "duration": duration,
        "has_video": has_video,
        "has_audio": has_audio,
        "streams": streams,
    }


def probe_duration(video: Path) -> float:
    info = probe_media(video)
    if info["duration"] <= 0:
        raise RuntimeError(f"Could not read duration from {video}")
    return info["duration"]


def pick_timestamp(duration: float, at: float | None) -> float:
    """Pick a mid-clip frame by default (usually a clearer dance pose)."""
    if duration <= 0:
        raise ValueError("Video duration must be positive")
    if at is not None:
        if at < 0 or at >= duration:
            raise ValueError(f"--at {at} is outside video duration {duration:.2f}s")
        # Keep a tiny margin from the end for keyframe seek safety
        return min(at, max(duration - 0.05, 0.0))
    # Slightly after start to avoid fade-in / black frames.
    return max(0.0, min(duration * 0.35, max(duration - 0.05, 0.0)))


def _run_ffmpeg(cmd: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, capture_output=True, text=True)


def extract_frame(video: Path, out_path: Path, at: float) -> Path:
    ffmpeg = _require_ffmpeg()
    out_path.parent.mkdir(parents=True, exist_ok=True)

    # Try accurate seek: -ss after -i is slower but more reliable on odd TikTok files.
    # Also try -ss before -i first (fast), then fallback.
    attempts = [
        [
            ffmpeg,
            "-y",
            "-ss",
            f"{at:.3f}",
            "-i",
            str(video),
            "-frames:v",
            "1",
            "-q:v",
            "2",
            str(out_path),
        ],
        [
            ffmpeg,
            "-y",
            "-i",
            str(video),
            "-ss",
            f"{at:.3f}",
            "-frames:v",
            "1",
            "-q:v",
            "2",
            str(out_path),
        ],
        # Absolute fallback: first frame
        [
            ffmpeg,
            "-y",
            "-i",
            str(video),
            "-frames:v",
            "1",
            "-q:v",
            "2",
            str(out_path),
        ],
    ]

    errors: list[str] = []
    for cmd in attempts:
        if out_path.exists():
            out_path.unlink(missing_ok=True)
        result = _run_ffmpeg(cmd)
        if result.returncode == 0 and out_path.exists() and out_path.stat().st_size > 0:
            return out_path
        errors.append(
            f"cmd={' '.join(cmd[-8:])} rc={result.returncode}\n"
            f"{(result.stderr or result.stdout or '')[-800:]}"
        )

    raise RuntimeError(
        "Failed to extract video frame. "
        "Source may be audio-only or corrupt (common when TikTok download picks mp3).\n"
        + "\n---\n".join(errors[-2:])
    )


def extract_audio(video: Path, out_path: Path) -> Path:
    """Copy audio stream when possible; fall back to AAC."""
    ffmpeg = _require_ffmpeg()
    out_path.parent.mkdir(parents=True, exist_ok=True)

    copy_cmd = [
        ffmpeg,
        "-y",
        "-i",
        str(video),
        "-vn",
        "-acodec",
        "copy",
        str(out_path),
    ]
    result = _run_ffmpeg(copy_cmd)
    if result.returncode == 0 and out_path.exists() and out_path.stat().st_size > 0:
        return out_path

    aac_path = out_path.with_suffix(".m4a")
    encode_cmd = [
        ffmpeg,
        "-y",
        "-i",
        str(video),
        "-vn",
        "-acodec",
        "aac",
        "-b:a",
        "192k",
        str(aac_path),
    ]
    result = _run_ffmpeg(encode_cmd)
    if result.returncode != 0 or not aac_path.exists() or aac_path.stat().st_size == 0:
        raise RuntimeError(
            "No usable audio track found. Source video may be silent.\n"
            f"{(result.stderr or '')[-800:]}"
        )
    return aac_path


def extract_assets(
    video: Path,
    out_dir: Path,
    *,
    at: float | None = None,
    frame_name: str = "frame.jpg",
    audio_name: str = "audio.m4a",
) -> dict[str, Path | float]:
    video = video.resolve()
    if not video.is_file():
        raise FileNotFoundError(f"Video not found: {video}")

    out_dir = out_dir.resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    info = probe_media(video)
    if not info["has_video"]:
        codecs = ", ".join(
            f"{s.get('codec_type')}:{s.get('codec_name')}" for s in info["streams"]
        )
        raise RuntimeError(
            f"Source has no video stream (only: {codecs or 'none'}). "
            f"File: {video}\n"
            "TikTok download likely grabbed audio-only. "
            "Re-run with updated yt-dlp / another link."
        )

    duration = info["duration"]
    if duration <= 0:
        raise RuntimeError(f"Invalid duration for {video}")

    ts = pick_timestamp(duration, at)
    frame_path = extract_frame(video, out_dir / frame_name, ts)
    audio_path = extract_audio(video, out_dir / audio_name)

    meta = {
        "video": video,
        "duration": duration,
        "timestamp": ts,
        "frame": frame_path,
        "audio": audio_path,
    }
    (out_dir / "extract_meta.json").write_text(
        json.dumps(
            {
                "video": str(video),
                "duration": duration,
                "timestamp": ts,
                "frame": str(frame_path),
                "audio": str(audio_path),
                "has_video": True,
                "has_audio": info["has_audio"],
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return meta
