# Video Clone MVP (Path A)

**Input:** link TikTok + ảnh mặt/nền cố định (mặc định `assets/`)  
**Output:** multi-shot nhảy trend TikTok + nhạc gốc đủ thời lượng

Mọi path mặc định **bám theo thư mục project** — clone máy khác vẫn chạy, không hardcode ổ đĩa.

## Luồng

```
assets/face.jpg + assets/background.jpg   (hoặc thư mục assets đã chọn)
              +
     link TikTok  ──SnapTik (fallback TikWM / yt-dlp)──► source.mp4
              │
         extract + compose ──► hero.jpg + audio + animate_prompts.md
              │
         Grok multi-shot TikTok animate ──► chain ──► final.mp4
              │
         publish ──► video_final_outputs/<run_id>.mp4
```

## Cài đặt (mới clone)

### Yêu cầu máy

| Thứ | Ghi chú |
|-----|---------|
| Python 3.10+ | `python --version` |
| FFmpeg | `ffmpeg -version` (phải có trên PATH) |
| Mạng | pip + model rembg/onnx lần đầu |

### Cách nhanh (khuyến nghị)

```powershell
cd path\to\video-clone-mvp
.\run_ui.bat
```

`run_ui.bat` tự:

1. Tạo `.venv` nếu chưa có  
2. `pip install -r requirements.txt`  
3. Mở UI tại **http://localhost:8502**

### Cách tay (CLI)

```powershell
cd path\to\video-clone-mvp
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

## Ảnh cố định (face + background)

Mặc định trong project:

```
video-clone-mvp/
  assets/
    face.jpg          # hoặc .png / .webp
    background.jpg    # hoặc bg.jpg / .png / .webp
```

- Đổi 2 file này = đổi mặt/nền cho **mọi** run sau  
- Không upload từng run qua UI  
- Có thể chọn thư mục khác (UI tab **Đường dẫn & ảnh**) — path được cache

```powershell
.\.venv\Scripts\python.exe -m video_clone assets
```

## UI

```powershell
.\run_ui.bat
# → http://localhost:8502
```

1. Tab **Đường dẫn & ảnh** — kiểm tra face/bg, (tuỳ chọn) chọn assets/finals  
2. Tab **Tạo run (TikTok)** — dán link TikTok  
3. **Tải TikTok + chuẩn bị run**  
4. Copy tin nhắn → chat Grok: `làm tiếp <run_id>`

### Đường dẫn

| Path | Mặc định | Chọn được? |
|------|----------|------------|
| Project | thư mục chứa `app.py` | Không (tự theo repo) |
| Work | `work/` | Không |
| Assets | `assets/` | Có — cache trong `work/settings.json` |
| Finals | `video_final_outputs/` | Có — cache trong `work/settings.json` |

- Path **trong** project được lưu dạng relative (portable khi clone)  
- Path **ngoài** project lưu absolute (theo máy)  
- Cache hỏng / không tồn tại → fallback về default project  
- `work/` đã gitignore — settings local không theo git

## CLI

```powershell
.\.venv\Scripts\Activate.ps1

# Chỉ tải video
python -m video_clone download --url "https://www.tiktok.com/@.../video/..." --out-dir work\downloads\test

# Full prepare từ link TikTok (dùng assets face + background)
python -m video_clone pipeline --tiktok-url "https://vm.tiktok.com/....."

# Hoặc video local (vẫn dùng face/bg cố định)
python -m video_clone pipeline --video path\to\dance.mp4 --out-dir work\run_local
```

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
video-clone-mvp/
  video_final_outputs/
    run_YYYYMMDD_HHMMSS.mp4
    ...
```

`assemble` tự copy; publish tay:

```powershell
python -m video_clone publish --video work\run_xxx\final.mp4 --run-id run_xxx
```

## Lệnh

| Lệnh | Việc |
|------|------|
| `assets` | Xem path face/bg đang active |
| `download` | Tải TikTok (SnapTik → TikWM → yt-dlp) |
| `pipeline --tiktok-url` | Tải + extract + compose + prompts |
| `plan` / `prompts` | Prompt pack |
| `last-frame` / `concat` / `assemble` | Ghép multi-shot + nhạc + publish |
| `publish` | Copy final → `<finals_dir>/<run>.mp4` |
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

### Import / Streamlit lỗi module cũ

Tắt hẳn cửa sổ `run_ui.bat` (Ctrl+C), xóa cache rồi chạy lại:

```powershell
Remove-Item -Recurse -Force video_clone\__pycache__ -ErrorAction SilentlyContinue
.\run_ui.bat
```

## Giới hạn

- Không copy 1:1 choreography video gốc (Path A)  
- Tải TikTok phụ thuộc mạng / region / provider  
- Một số post TikTok (slideshow ảnh / audio) **không có video**  
- Consent + bản quyền: user tự chịu  

## Cấu trúc

```
video-clone-mvp/
  assets/                 # face.jpg + background.jpg (mặc định)
  video_final_outputs/    # video xuất bản <run_id>.mp4
  work/                   # runs, downloads, settings.json (gitignore)
  app.py                  # Streamlit UI
  run_ui.bat              # setup venv + start UI
  requirements.txt
  video_clone/
    config.py             # path động + cache portable
    download.py           # SnapTik / TikWM / yt-dlp
    compose.py
    pipeline_run.py
    style.py
    ...
```
