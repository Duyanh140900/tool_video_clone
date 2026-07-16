"""
Default dance style for all future video clones.

Every image_to_video shot uses TikTok viral-trend energy:
snappy, beat-driven, phone-vertical challenge vibes.
Multi-shot chains continue pose-to-pose with NEW phrases (never loop).
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Sequence

# ---------------------------------------------------------------------------
# Canonical default — change here to re-skin the whole tool.
# ---------------------------------------------------------------------------
DEFAULT_STYLE_ID = "tiktok_trend"
DEFAULT_STYLE_NAME = "TikTok viral trend dance"

# Shared identity lock for every shot (appended to each prompt).
IDENTITY_LOCK = (
    "same face identity, same outfit, same background, "
    "vertical phone framing, camera locked, full body visible when possible"
)

# Style DNA — always included so models stay on-trend.
STYLE_DNA = (
    "viral TikTok dance challenge energy: sharp on-beat moves, "
    "snappy arm and hand gestures, hip and shoulder accents, "
    "high-energy short-form trend vibe"
)

# Ordered phrase library. Shots cycle through this list so longer audio
# still gets variety instead of repeating the same motion description.
TIKTOK_PHRASES: tuple[str, ...] = (
    "sharp shoulder pops, hip sways on the beat, pointing hand gestures and a quick body roll",
    "cross-step side to side, finger-gun points to camera then chest, hair-flip energy, sharp arm waves",
    "heel-toe steps, hip bounce, clap-and-point combo, then a signature freeze pose near the face",
    "quick head tilts with the beat, chest pops, hand hearts then open palms, bounce in place",
    "side lean + knee bounce, arm wave from side to overhead, playful wink timing, step-touch",
    "hip circles into body roll, point-down then point-up, swish turn a quarter step, smile to camera",
    "march-in-place with sharp elbows, shoulder shimmy, two claps, then pose with one hand on hip",
    "slide step left-right, hair toss energy, finger snap accents, end with both arms out open pose",
)


@dataclass(frozen=True)
class ShotPrompt:
    index: int  # 1-based
    duration: int  # 6 or 10
    phrase: str
    prompt: str
    source_image: str  # hint for Grok / operator


def _phrase_for_index(index_1based: int) -> str:
    return TIKTOK_PHRASES[(index_1based - 1) % len(TIKTOK_PHRASES)]


def build_shot_prompt(
    index_1based: int,
    duration: int,
    *,
    continuing: bool | None = None,
) -> str:
    """
    Full image_to_video prompt for one shot.

    Shot 1 starts the challenge; later shots explicitly continue from last pose.
    """
    if continuing is None:
        continuing = index_1based > 1
    phrase = _phrase_for_index(index_1based)

    if continuing:
        lead = (
            f"She continues the viral TikTok trend dance into a new phrase: {phrase}"
        )
    else:
        lead = f"She hits a viral TikTok trend dance: {phrase}"

    return (
        f"{lead}, {STYLE_DNA}, {IDENTITY_LOCK}, "
        f"energetic but natural motion for about {duration} seconds"
    )


def build_shot_plan(
    durations: Sequence[int],
    *,
    hero_name: str = "hero_refined.jpg",
) -> list[ShotPrompt]:
    """Build ordered shot prompts from plan_shot_durations() output."""
    shots: list[ShotPrompt] = []
    for i, dur in enumerate(durations, start=1):
        if i == 1:
            source = hero_name
        else:
            source = f"shot{i - 1:02d}_last.jpg"
        shots.append(
            ShotPrompt(
                index=i,
                duration=int(dur),
                phrase=_phrase_for_index(i),
                prompt=build_shot_prompt(i, int(dur)),
                source_image=source,
            )
        )
    return shots


def write_prompt_bundle(
    out_dir: Path,
    shots: Sequence[ShotPrompt],
    *,
    audio_seconds: float | None = None,
) -> dict[str, Path]:
    """
    Write animate_prompts.json + animate_prompts.md for the operator / Grok.
    Returns paths written.
    """
    out_dir = out_dir.resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    payload = {
        "style_id": DEFAULT_STYLE_ID,
        "style_name": DEFAULT_STYLE_NAME,
        "rules": [
            "Do NOT loop the same clip to fill audio.",
            "Each shot must use a NEW TikTok phrase and continue from previous last frame.",
            "Keep face, outfit, background identity locked across shots.",
            "Prefer 720p vertical; duration 6 or 10 seconds as listed.",
        ],
        "audio_seconds": audio_seconds,
        "identity_lock": IDENTITY_LOCK,
        "style_dna": STYLE_DNA,
        "shots": [asdict(s) for s in shots],
    }

    json_path = out_dir / "animate_prompts.json"
    json_path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    lines = [
        f"# Animate prompts - {DEFAULT_STYLE_NAME}",
        "",
        f"Style id: `{DEFAULT_STYLE_ID}`",
        "",
        "## Rules",
        "",
        "- **No loop** of the same clip.",
        "- Each shot = **new TikTok phrase**, continue from last frame.",
        "- Lock face / outfit / background.",
        "",
    ]
    if audio_seconds is not None:
        lines.append(f"Audio length: **{audio_seconds:.2f}s**")
        lines.append("")

    for s in shots:
        lines.extend(
            [
                f"## Shot {s.index:02d} - {s.duration}s",
                "",
                f"- Source image: `{s.source_image}`",
                f"- Phrase: {s.phrase}",
                "",
                "```",
                s.prompt,
                "```",
                "",
            ]
        )
        if s.index > 1:
            lines.extend(
                [
                    "```powershell",
                    f"python -m video_clone last-frame "
                    f"--video shot{s.index - 1:02d}.mp4 "
                    f"--out shot{s.index - 1:02d}_last.jpg",
                    "```",
                    "",
                ]
            )

    lines.extend(
        [
            "## After all shots",
            "",
            "```powershell",
            "python -m video_clone concat --clips shot01.mp4 shot02.mp4 ... --out chain.mp4",
            "python -m video_clone assemble --video chain.mp4 --audio audio.m4a --out final.mp4",
            "```",
            "",
        ]
    )

    md_path = out_dir / "animate_prompts.md"
    md_path.write_text("\n".join(lines), encoding="utf-8")

    return {"json": json_path, "md": md_path}


def print_shot_plan(shots: Sequence[ShotPrompt], *, audio_seconds: float | None = None) -> None:
    print(f"style    : {DEFAULT_STYLE_NAME} ({DEFAULT_STYLE_ID})")
    if audio_seconds is not None:
        print(f"audio    : {audio_seconds:.2f}s")
    print(f"shots    : {[s.duration for s in shots]}  (no loop; continuous TikTok phrases)")
    print()
    for s in shots:
        print(f"--- shot{s.index:02d} ({s.duration}s) from {s.source_image} ---")
        print(f"phrase : {s.phrase}")
        print(f"prompt : {s.prompt}")
        print()
