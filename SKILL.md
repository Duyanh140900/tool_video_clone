---
name: video-clone-mvp
description: >
  Path A video clone from TikTok URL + fixed assets/face.jpg and
  assets/background.jpg. Multi-shot TikTok trend dance, no loop, full audio.
  Use when user pastes TikTok link, says video-clone, or "làm tiếp run".
---

# Video Clone MVP — TikTok URL + fixed face/bg

Local: `C:\source_code\tool\video-clone-mvp`

## Inputs (new contract)

| Input | Source |
|-------|--------|
| Face | **Fixed** `assets/face.jpg` (or face.png/webp) |
| Background | **Fixed** `assets/background.jpg` (or bg.*) |
| Dance video | **TikTok URL** → yt-dlp download (not manual upload) |

```powershell
python -m video_clone assets
python -m video_clone pipeline --tiktok-url "https://www.tiktok.com/@.../video/..."
# or UI: run_ui.bat → paste URL
```

## UI

```powershell
cd C:\source_code\tool\video-clone-mvp
.\run_ui.bat
# http://localhost:8502
```

Writes `work/<run_id>/` + `work/LATEST.json`.

## When user says "làm tiếp" / pastes GROK.txt

1. `python -m video_clone latest` or read `work/LATEST.json`
2. Fixed face/bg already applied in `hero.jpg`; refine with `image_edit` if needed → `hero_refined.jpg`
3. Multi-shot **TikTok trend** from `animate_prompts.md` (no loop)
4. Concat + assemble full audio → `work/<run_id>/final.mp4`
5. **Always publish** to `video_final_outputs/<run_id>.mp4` (assemble does this by default)

Delivery folder: `C:\source_code\tool\video-clone-mvp\video_final_outputs\`

## Defaults

| Setting | Value |
|---------|--------|
| Dance | `tiktok_trend` (`style.py`) |
| Loop | Forbidden unless user accepts |
| Audio | Full track |
| Shots | 6s / 10s continuous phrases |

## Download

Primary: **SnapTik** (`video_clone/download.py` + `snaptik_decoder.py`).  
Fallbacks: TikWM JSON API → yt-dlp.

```powershell
python -m video_clone download --url "https://..." --provider snaptik
```

If all fail: update deps, check public video URL (not slideshow/private).

## Hard rules

1. Always use fixed assets unless user overrides paths.
2. Prefer TikTok URL path over local file upload.
3. No looping same dance clip.
4. Keep face/outfit/bg identity locked across shots.
