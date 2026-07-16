"""CLI for Video Clone MVP (path A: still compose + TikTok multi-shot + music)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .assemble import (
    infer_run_id_from_paths,
    mux_audio,
    probe_duration,
    publish_final_output,
)
from .chain import concat_videos, extract_last_frame, plan_shot_durations
from .compose import compose_hero
from .config import (
    ASSETS_DIR,
    assets_status,
    get_assets_dir,
    get_finals_dir,
    resolve_bg,
    resolve_face,
)
from .download import download_tiktok_video, is_tiktok_url
from .extract import extract_assets
from .pipeline_run import prepare_from_tiktok_url, prepare_run, read_latest
from .style import (
    DEFAULT_STYLE_ID,
    DEFAULT_STYLE_NAME,
    build_shot_plan,
    build_shot_prompt,
    print_shot_plan,
    write_prompt_bundle,
)


def _cmd_extract(args: argparse.Namespace) -> int:
    meta = extract_assets(
        Path(args.video),
        Path(args.out_dir),
        at=args.at,
    )
    print(f"duration : {meta['duration']:.2f}s")
    print(f"timestamp: {meta['timestamp']:.2f}s")
    print(f"frame    : {meta['frame']}")
    print(f"audio    : {meta['audio']}")
    return 0


def _cmd_compose(args: argparse.Namespace) -> int:
    face = Path(args.face) if args.face else resolve_face()
    bg = Path(args.bg) if args.bg else resolve_bg()
    out = compose_hero(
        Path(args.frame),
        face,
        bg,
        Path(args.out),
        skip_face=args.skip_face,
        skip_bg=args.skip_bg,
    )
    print(f"hero     : {out}")
    print(f"face     : {face}")
    print(f"bg       : {bg}")
    print(f"style    : {DEFAULT_STYLE_NAME}")
    return 0


def _cmd_assets(args: argparse.Namespace) -> int:
    st = assets_status()
    print(f"assets_dir: {st['assets_dir']}")
    print(f"default   : {ASSETS_DIR.resolve()}")
    print(f"is_default: {st.get('is_default', True)}")
    print(f"face      : {st['face'] or 'MISSING'}")
    print(f"bg        : {st['bg'] or 'MISSING'}")
    print(f"ok        : {st['ok']}")
    if not st["ok"]:
        print(f"Put face.jpg + background.jpg into {get_assets_dir()}")
        return 1
    return 0


def _cmd_download(args: argparse.Namespace) -> int:
    out_dir = Path(args.out_dir)
    providers = None
    if getattr(args, "provider", "auto") and args.provider != "auto":
        providers = (args.provider,)
    path = (
        download_tiktok_video(args.url, out_dir, providers=providers)
        if providers
        else download_tiktok_video(args.url, out_dir)
    )
    print(f"downloaded: {path}")
    meta = out_dir / "download_meta.json"
    if meta.is_file():
        print(f"meta      : {meta.read_text(encoding='utf-8').strip()}")
    return 0


def _cmd_assemble(args: argparse.Namespace) -> int:
    if args.loop_video:
        mode = "loop_video"
    elif args.cut_to_video:
        mode = "cut_to_video"
    else:
        mode = "trim_to_audio"
    video = Path(args.video)
    audio = Path(args.audio)
    out_path = Path(args.out)
    rid = args.run_id or infer_run_id_from_paths(out_path, video, audio)
    out = mux_audio(
        video,
        audio,
        out_path,
        mode=mode,
        run_id=rid,
        publish=not args.no_publish,
    )
    print(f"work copy: {out_path.resolve() if out_path.exists() else out_path}")
    if not args.no_publish and rid:
        print(f"named as : {get_finals_dir() / (rid + '.mp4')}")
    return 0


def _cmd_publish(args: argparse.Namespace) -> int:
    dest = publish_final_output(Path(args.video), run_id=args.run_id)
    print(f"published: {dest}")
    return 0


def _cmd_last_frame(args: argparse.Namespace) -> int:
    out = extract_last_frame(Path(args.video), Path(args.out))
    print(f"last frame: {out}")
    # Infer next shot index from filename if possible; else generic continuing prompt.
    next_index = args.next_shot if args.next_shot else 2
    duration = args.duration
    prompt = build_shot_prompt(next_index, duration, continuing=True)
    print(f"style     : {DEFAULT_STYLE_NAME}")
    print(f"next shot : shot{next_index:02d} ({duration}s) — TikTok phrase (continuing)")
    print(f"prompt    : {prompt}")
    return 0


def _cmd_concat(args: argparse.Namespace) -> int:
    clips = [Path(c) for c in args.clips]
    out = concat_videos(
        clips,
        Path(args.out),
        width=args.width,
        height=args.height,
        fps=args.fps,
    )
    print(f"chain    : {out}")
    print(f"duration : {probe_duration(out):.2f}s")
    return 0


def _cmd_plan(args: argparse.Namespace) -> int:
    audio = Path(args.audio)
    dur = probe_duration(audio)
    durations = plan_shot_durations(dur)
    shots = build_shot_plan(durations, hero_name=args.hero_name)
    print_shot_plan(shots, audio_seconds=dur)

    if args.out_dir:
        paths = write_prompt_bundle(
            Path(args.out_dir),
            shots,
            audio_seconds=dur,
        )
        print(f"wrote    : {paths['json']}")
        print(f"wrote    : {paths['md']}")
    else:
        print("Tip: add --out-dir work\\run1 to write animate_prompts.json / .md")
    return 0


def _cmd_prompts(args: argparse.Namespace) -> int:
    """Write TikTok animate prompt bundle for a work directory."""
    audio = Path(args.audio)
    out_dir = Path(args.out_dir)
    dur = probe_duration(audio)
    durations = plan_shot_durations(dur)
    shots = build_shot_plan(durations, hero_name=args.hero_name)
    paths = write_prompt_bundle(out_dir, shots, audio_seconds=dur)
    print_shot_plan(shots, audio_seconds=dur)
    print(f"wrote    : {paths['json']}")
    print(f"wrote    : {paths['md']}")
    return 0


def _cmd_pipeline(args: argparse.Namespace) -> int:
    out_arg = Path(args.out_dir)
    if out_arg.name == "work" and len(out_arg.parts) == 1:
        out_dir = None
        run_id = None
    else:
        out_dir = out_arg
        run_id = out_arg.name

    print("==> prepare (download if URL + fixed assets + prompts)")
    if args.tiktok_url:
        if not is_tiktok_url(args.tiktok_url):
            raise ValueError(f"Not a TikTok URL: {args.tiktok_url}")
        print(f"    url   : {args.tiktok_url}")
        result = prepare_from_tiktok_url(
            args.tiktok_url,
            out_dir=out_dir,
            run_id=run_id,
            at=args.at,
            skip_face=args.skip_face,
            skip_bg=args.skip_bg,
        )
    else:
        if not args.video:
            raise ValueError("Provide --tiktok-url or --video")
        face = Path(args.face) if args.face else resolve_face()
        bg = Path(args.bg) if args.bg else resolve_bg()
        result = prepare_run(
            video=Path(args.video),
            face=face,
            bg=bg,
            out_dir=out_dir,
            run_id=run_id,
            at=args.at,
            skip_face=args.skip_face,
            skip_bg=args.skip_bg,
        )

    print(f"    run   : {result['run_id']}")
    print(f"    out   : {result['out_dir']}")
    print(f"    face  : {result['face']}")
    print(f"    bg    : {result['bg']}")
    print(f"    hero  : {result['hero']}")
    print(f"    audio : {result['audio']} ({result['audio_seconds']:.1f}s)")
    print(f"    style : {result['style_name']} ({result['style_id']})")
    print(f"    prompts: {result['prompts_md']}")

    if args.animated:
        print("==> mux animated chain + original audio")
        final = Path(args.out) if args.out else Path(result["out_dir"]) / "final.mp4"
        mux_audio(
            Path(args.animated),
            Path(result["audio"]),
            final,
            mode="trim_to_audio",
        )
        print(f"    final : {final}")
        return 0

    print()
    print("==> Next: paste this to Grok (or open UI GROK.txt)")
    print(result["grok_message"])
    print()
    print("UI: double-click run_ui.bat  ->  http://localhost:8502")
    return 0


def _cmd_latest(args: argparse.Namespace) -> int:
    latest = read_latest()
    if not latest:
        print("No latest run. Create one via UI or pipeline.")
        return 1
    print(json.dumps(latest, indent=2, ensure_ascii=False))
    print()
    print(latest.get("grok_message", ""))
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="video_clone",
        description=(
            f"Video Clone MVP (path A): extract → face+bg → multi-shot "
            f"{DEFAULT_STYLE_NAME} animate (no loop) → mux music."
        ),
    )
    sub = p.add_subparsers(dest="command", required=True)

    e = sub.add_parser("extract", help="Extract frame + audio from source video")
    e.add_argument("--video", required=True, help="Source dance video")
    e.add_argument("--out-dir", default="work", help="Output folder")
    e.add_argument(
        "--at",
        type=float,
        default=None,
        help="Timestamp in seconds for the still frame (default: ~35%% into clip)",
    )
    e.set_defaults(func=_cmd_extract)

    c = sub.add_parser("compose", help="Face swap + background replace on a still")
    c.add_argument("--frame", required=True, help="Source still (from extract)")
    c.add_argument(
        "--face",
        default=None,
        help=f"Face photo (default: fixed {ASSETS_DIR / 'face.jpg'})",
    )
    c.add_argument(
        "--bg",
        default=None,
        help=f"Background image (default: fixed {ASSETS_DIR / 'background.jpg'})",
    )
    c.add_argument("--out", default="work/hero.jpg", help="Output hero still")
    c.add_argument("--skip-face", action="store_true", help="Do not swap face")
    c.add_argument("--skip-bg", action="store_true", help="Do not replace background")
    c.set_defaults(func=_cmd_compose)

    ast = sub.add_parser("assets", help="Show fixed face/background asset paths")
    ast.set_defaults(func=_cmd_assets)

    dl = sub.add_parser(
        "download",
        help="Download a TikTok video (SnapTik → TikWM → yt-dlp)",
    )
    dl.add_argument("--url", required=True, help="TikTok URL")
    dl.add_argument("--out-dir", default="work/downloads", help="Download folder")
    dl.add_argument(
        "--provider",
        default="auto",
        choices=("auto", "snaptik", "tikwm", "ytdlp"),
        help="Download provider (default: auto = snaptik then fallbacks)",
    )
    dl.set_defaults(func=_cmd_download)

    a = sub.add_parser(
        "assemble",
        help="Mux video + audio; also copy to video_final_outputs/<run_id>.mp4",
    )
    a.add_argument("--video", required=True, help="Animated / chained clip")
    a.add_argument("--audio", required=True, help="Audio from extract step")
    a.add_argument("--out", default="work/final.mp4", help="Work-dir final path")
    a.add_argument(
        "--run-id",
        default=None,
        help="Name for video_final_outputs/<run_id>.mp4 (default: parent work folder)",
    )
    a.add_argument(
        "--no-publish",
        action="store_true",
        help="Do not copy into video_final_outputs/",
    )
    a.add_argument(
        "--cut-to-video",
        action="store_true",
        help="End when video ends (ignore remaining audio)",
    )
    a.add_argument(
        "--loop-video",
        action="store_true",
        help="Loop the same clip to fill audio (NOT for TikTok continuous dance)",
    )
    a.set_defaults(func=_cmd_assemble)

    pub = sub.add_parser(
        "publish",
        help="Copy an existing final.mp4 into video_final_outputs/<run_id>.mp4",
    )
    pub.add_argument("--video", required=True, help="Path to final.mp4")
    pub.add_argument(
        "--run-id",
        default=None,
        help="Output name (default: parent folder name under work/)",
    )
    pub.set_defaults(func=_cmd_publish)

    lf = sub.add_parser(
        "last-frame",
        help="Extract last frame + print next TikTok continuing prompt",
    )
    lf.add_argument("--video", required=True, help="Shot video")
    lf.add_argument("--out", default="work/last.jpg", help="Output JPEG path")
    lf.add_argument(
        "--next-shot",
        type=int,
        default=None,
        help="1-based index of the NEXT shot (default: 2)",
    )
    lf.add_argument(
        "--duration",
        type=int,
        default=6,
        choices=(6, 10),
        help="Duration for the next image_to_video prompt",
    )
    lf.set_defaults(func=_cmd_last_frame)

    cc = sub.add_parser(
        "concat",
        help="Join multiple dance shots into one continuous video (no loop)",
    )
    cc.add_argument(
        "--clips",
        nargs="+",
        required=True,
        help="Shot files in order, e.g. shot01.mp4 shot02.mp4 shot03.mp4",
    )
    cc.add_argument("--out", default="work/chain.mp4", help="Output chain path")
    cc.add_argument("--width", type=int, default=720)
    cc.add_argument("--height", type=int, default=1280)
    cc.add_argument("--fps", type=int, default=24)
    cc.set_defaults(func=_cmd_concat)

    pln = sub.add_parser(
        "plan",
        help=f"Plan multi-shot {DEFAULT_STYLE_NAME} durations + prompts",
    )
    pln.add_argument("--audio", required=True, help="Extracted audio or source video")
    pln.add_argument(
        "--out-dir",
        default=None,
        help="If set, write animate_prompts.json and animate_prompts.md",
    )
    pln.add_argument(
        "--hero-name",
        default="hero_refined.jpg",
        help="Source image name for shot01 in the prompt pack",
    )
    pln.set_defaults(func=_cmd_plan)

    pr = sub.add_parser(
        "prompts",
        help=f"Write {DEFAULT_STYLE_NAME} image_to_video prompt pack for a run",
    )
    pr.add_argument("--audio", required=True, help="Extracted audio track")
    pr.add_argument("--out-dir", required=True, help="Work directory for this run")
    pr.add_argument(
        "--hero-name",
        default="hero_refined.jpg",
        help="Source image name for shot01",
    )
    pr.set_defaults(func=_cmd_prompts)

    pl = sub.add_parser(
        "pipeline",
        help="TikTok URL (or local video) + fixed assets → prepare run",
    )
    pl.add_argument(
        "--tiktok-url",
        default=None,
        help="TikTok link (preferred). Downloads then prepares run.",
    )
    pl.add_argument(
        "--video",
        default=None,
        help="Local video path (optional if --tiktok-url is set)",
    )
    pl.add_argument(
        "--face",
        default=None,
        help="Override fixed face (default: assets/face.jpg)",
    )
    pl.add_argument(
        "--bg",
        default=None,
        help="Override fixed background (default: assets/background.jpg)",
    )
    pl.add_argument(
        "--out-dir",
        default="work",
        help='Output folder (default "work" creates work/run_YYYYMMDD_HHMMSS)',
    )
    pl.add_argument("--at", type=float, default=None, help="Frame timestamp (s)")
    pl.add_argument("--skip-face", action="store_true")
    pl.add_argument("--skip-bg", action="store_true")
    pl.add_argument(
        "--animated",
        default=None,
        help="If set, mux this chain/clip with extracted audio",
    )
    pl.add_argument(
        "--out",
        default=None,
        help="Final path when --animated is provided",
    )
    pl.set_defaults(func=_cmd_pipeline)

    lt = sub.add_parser(
        "latest",
        help="Show latest UI/CLI handoff (work/LATEST.json) for Grok",
    )
    lt.set_defaults(func=_cmd_latest)

    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args))
    except Exception as exc:  # noqa: BLE001 — CLI surface
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
