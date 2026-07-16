# Video Clone MVP (Path A)

**Input:** link TikTok + ảnh mặt/nền **cố định** trong `assets/`  
**Output:** multi-shot nhảy trend TikTok + nhạc gốc đủ thời lượng.

## Luồng

```
assets/face.jpg + assets/background.jpg   (cố định)
              +
     link TikTok  ──SnapTik (fallback TikWM / yt-dlp)──► source.mp4
              │
         extract + compose ──► hero.jpg + audio + animate_prompts.md
              │
         Grok multi-shot TikTok animate ──► chain ──► final.mp4
```

## Ảnh cố định

Thư mục:

```
C:\source_code\tool\video-clone-mvp\assets\
  face.jpg
  background.jpg
```

Đổi 2 file này = đổi mặt/nền cho **mọi** run sau. Không upload qua UI.

```powershell
python -m video_clone assets
```

## UI (khuyến nghị)

```powershell
cd C:\source_code\tool\video-clone-mvp
.\run_ui.bat
```

→ http://localhost:8502  

1. Kiểm tra tab **Ảnh cố định**  
2. Dán **link TikTok**  
3. **Tải TikTok + chuẩn bị run**  
4. Copy tin nhắn → chat Grok: `làm tiếp <run_id>`

## CLI

```powershell
.\.venv\Scripts\Activate.ps1

# Chỉ tải video
python -m video_clone download --url "https://www.tiktok.com/@.../video/..." --out-dir work\downloads\test

# Full prepare từ link TikTok (dùng assets/face + background)
python -m video_clone pipeline --tiktok-url "https://vm.tiktok.com/....."

# Hoặc video local (vẫn dùng face/bg cố định)
python -m video_clone pipeline --video path\to\dance.mp4 --out-dir work\run_local
```

## Cài đặt

```powershell
cd C:\source_code\tool\video-clone-mvp
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Cần: Python 3.10+, FFmpeg, mạng (tải TikTok + model rembg lần đầu).

## Sau khi prepare

Grok:

1. Refine `hero.jpg` → `hero_refined.jpg`  
2. Multi-shot theo `animate_prompts.md` (style TikTok, **không loop**)  
3. `concat` + `assemble` → `work/<run>/final.mp4` **và**  
   `video_final_outputs/<run_id>.mp4`

```powershell
python -m video_clone latest
```

### Thư mục video xong

```
C:\source_code\tool\video-clone-mvp\video_final_outputs\
  run_20260716_121002.mp4
  run1.mp4
  ...
```

`assemble` tự copy; publish tay:

```powershell
python -m video_clone publish --video work\run_xxx\final.mp4 --run-id run_xxx
```

## Lệnh

| Lệnh | Việc |
|------|------|
| `assets` | Xem path face/bg cố định |
| `download` | Tải TikTok (SnapTik → TikWM → yt-dlp) |
| `pipeline --tiktok-url` | Tải + extract + compose + prompts |
| `plan` / `prompts` | Prompt pack |
| `last-frame` / `concat` / `assemble` | Ghép multi-shot + nhạc + publish |
| `publish` | Copy final → `video_final_outputs/<run>.mp4` |
| `latest` | Handoff run mới nhất |

## Style nhảy

Mặc định `tiktok_trend` trong `video_clone/style.py`.

## Troubleshooting

### Download TikTok

Mặc định dùng **SnapTik** (`snaptik.app` reverse API), rồi fallback:

1. `snaptik` — primary  
2. `tikwm` — JSON API  
3. `ytdlp` — last resort  

```powershell
python -m video_clone download --url "https://..." --out-dir work\downloads\test
python -m video_clone download --url "https://..." --provider snaptik
python -m video_clone download --url "https://..." --provider tikwm
ffprobe work\downloads\test\source.mp4   # phải có codec_type=video
```

Nếu SnapTik đổi HTML/token, TikWM thường vẫn chạy.

## Giới hạn

- Không copy 1:1 choreography video gốc (Path A)  
- Tải TikTok phụ thuộc yt-dlp / mạng / region  
- Một số post TikTok (slideshow ảnh / audio) **không có video**  
- Consent + bản quyền: user tự chịu  

## Cấu trúc

```
video-clone-mvp/
  assets/           # face.jpg + background.jpg (FIXED)
  app.py            # Streamlit UI
  run_ui.bat
  video_clone/
    config.py
    download.py     # yt-dlp TikTok
    style.py
    pipeline_run.py
    ...
```
