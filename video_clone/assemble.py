"""Mux animated video with original audio track; publish finals by run name."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

from .config import WORK_ROOT, final_output_path, get_finals_dir


def publish_final_output(
    final_path: Path,
    *,
    run_id: str | None = None,
) -> Path:
    """
    Copy finished video into video_final_outputs/<run_id>.mp4.

    run_id defaults to the parent folder name when final lives under work/<run_id>/.
    """
    final_path = Path(final_path).resolve()
    if not final_path.is_file():
        raise FileNotFoundError(f"Final video not found: {final_path}")

    rid = (run_id or "").strip()
    if not rid:
        parent = final_path.parent
        try:
            parent.relative_to(WORK_ROOT.resolve())
            rid = parent.name
        except ValueError:
            rid = final_path.stem

    dest = final_output_path(rid)
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(final_path, dest)
    print(f"published: {dest}")
    return dest


def infer_run_id_from_paths(*paths: Path) -> str | None:
    """If any path is under work/<run_id>/..., return that run_id."""
    work = WORK_ROOT.resolve()
    for p in paths:
        try:
            rel = Path(p).resolve().relative_to(work)
        except ValueError:
            continue
        if rel.parts:
            return rel.parts[0]
    return None


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


def probe_duration(path: Path) -> float:
    ffprobe = _require_ffprobe()
    cmd = [
        ffprobe,
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "json",
        str(path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, check=True)
    data = json.loads(result.stdout)
    return float(data["format"]["duration"])


def mux_audio(
    video: Path,
    audio: Path,
    out_path: Path,
    *,
    mode: str = "trim_to_audio",
    run_id: str | None = None,
    publish: bool = True,
) -> Path:
    """
    Attach source music to the animated clip.

    modes:
      trim_to_audio (default) — use full audio; trim video if longer.
        Prefer a pre-chained multi-shot video that already covers the music.
      cut_to_video — end when the video ends (short AI clip).
      loop_video — loop the same clip until audio ends (last resort; not for dance continuity).

    When publish=True (default), also copies the result to
    video_final_outputs/<run_id>.mp4 (run_id inferred from work/ path if omitted).
    """
    ffmpeg = _require_ffmpeg()
    video = video.resolve()
    audio = audio.resolve()
    out_path = out_path.resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)

    if not video.is_file():
        raise FileNotFoundError(f"Video not found: {video}")
    if not audio.is_file():
        raise FileNotFoundError(f"Audio not found: {audio}")

    if mode not in {"trim_to_audio", "cut_to_video", "loop_video"}:
        raise ValueError(f"Unknown mode: {mode}")

    v_dur = probe_duration(video)
    a_dur = probe_duration(audio)

    if mode == "loop_video" and a_dur > v_dur + 0.05:
        cmd = [
            ffmpeg,
            "-y",
            "-stream_loop",
            "-1",
            "-i",
            str(video),
            "-i",
            str(audio),
            "-map",
            "0:v:0",
            "-map",
            "1:a:0",
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
            "-t",
            f"{a_dur:.3f}",
            "-movflags",
            "+faststart",
            str(out_path),
        ]
        mode_label = f"loop video ~{a_dur / v_dur:.1f}x (not continuous dance)"
    elif mode == "cut_to_video":
        cmd = [
            ffmpeg,
            "-y",
            "-i",
            str(video),
            "-i",
            str(audio),
            "-map",
            "0:v:0",
            "-map",
            "1:a:0",
            "-c:v",
            "copy",
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            "-shortest",
            "-movflags",
            "+faststart",
            str(out_path),
        ]
        mode_label = "cut to video length"
    else:
        # Full music length: video must already cover it (multi-shot chain).
        # If video is shorter, freeze last frame for the remainder.
        if v_dur + 0.05 < a_dur:
            pad = a_dur - v_dur
            # tpad adds freeze frames after last frame
            cmd = [
                ffmpeg,
                "-y",
                "-i",
                str(video),
                "-i",
                str(audio),
                "-filter_complex",
                f"[0:v]tpad=stop_mode=clone:stop_duration={pad:.3f},format=yuv420p[v]",
                "-map",
                "[v]",
                "-map",
                "1:a:0",
                "-c:v",
                "libx264",
                "-preset",
                "fast",
                "-crf",
                "18",
                "-c:a",
                "aac",
                "-b:a",
                "192k",
                "-t",
                f"{a_dur:.3f}",
                "-movflags",
                "+faststart",
                str(out_path),
            ]
            mode_label = (
                f"trim/pad to audio ({v_dur:.1f}s video + {pad:.1f}s freeze pad)"
            )
        else:
            cmd = [
                ffmpeg,
                "-y",
                "-i",
                str(video),
                "-i",
                str(audio),
                "-map",
                "0:v:0",
                "-map",
                "1:a:0",
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
                "-t",
                f"{a_dur:.3f}",
                "-movflags",
                "+faststart",
                str(out_path),
            ]
            mode_label = "full audio (trim video if longer)"

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(
            "ffmpeg mux failed:\n"
            + (result.stderr[-2000:] if result.stderr else result.stdout)
        )

    out_dur = probe_duration(out_path)
    print(f"video in : {v_dur:.2f}s")
    print(f"audio in : {a_dur:.2f}s")
    print(f"output   : {out_dur:.2f}s")
    print(f"mode     : {mode_label}")
    print(f"final    : {out_path}")

    if publish:
        rid = run_id or infer_run_id_from_paths(out_path, video, audio)
        try:
            publish_final_output(out_path, run_id=rid)
            print(f"folder   : {get_finals_dir()}")
        except Exception as exc:  # noqa: BLE001
            print(f"publish warning: {exc}")

    return out_path
