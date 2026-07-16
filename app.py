"""
Video Clone UI — dán link TikTok; mặt + nền lấy cố định từ assets/.

Chạy:
  streamlit run app.py
  hoặc double-click run_ui.bat
"""

from __future__ import annotations

from pathlib import Path

import streamlit as st

from video_clone.config import (
    ASSETS_DIR,
    FINAL_OUTPUTS_DIR,
    LATEST_POINTER,
    WORK_ROOT,
    assets_status,
)
from video_clone.download import is_tiktok_url
from video_clone.pipeline_run import new_run_id, prepare_from_tiktok_url, read_latest
from video_clone.style import DEFAULT_STYLE_NAME

ROOT = Path(__file__).resolve().parent

st.set_page_config(
    page_title="Video Clone",
    page_icon="🎬",
    layout="centered",
    initial_sidebar_state="collapsed",
)

st.markdown(
    """
<style>
  .block-container { max-width: 820px; padding-top: 1.25rem; }
  .stButton button { width: 100%; }
  .hint {
    background: #0f172a0d;
    border: 1px solid #64748b33;
    border-radius: 12px;
    padding: 0.9rem 1rem;
    font-size: 0.95rem;
    line-height: 1.45;
  }
  .ok {
    background: #052e16;
    color: #bbf7d0;
    border-radius: 12px;
    padding: 0.9rem 1rem;
  }
  .warn {
    background: #422006;
    color: #fed7aa;
    border-radius: 12px;
    padding: 0.9rem 1rem;
  }
</style>
""",
    unsafe_allow_html=True,
)

st.title("🎬 Video Clone")
st.caption(
    f"Dán **link TikTok** → tool tự tải video qua **SnapTik** "
    f"(fallback TikWM / yt-dlp). "
    f"Ảnh mặt + nền **cố định** trong `assets/`. "
    f"Style: **{DEFAULT_STYLE_NAME}**. "
    f"Xong thì nhắn Grok: *làm tiếp run …*"
)

status = assets_status()
tab_new, tab_assets, tab_latest = st.tabs(
    ["Tạo run (TikTok)", "Ảnh cố định", "Run gần nhất"]
)

with tab_assets:
    st.subheader("Thư mục assets (face + background cố định)")
    st.code(str(ASSETS_DIR), language=None)
    st.markdown(
        "Đặt file vào thư mục này (đổi file = đổi mặt/nền cho **mọi** run sau):"
    )
    st.markdown(
        "- `face.jpg` (hoặc `.png` / `.webp`)\n"
        "- `background.jpg` (hoặc `bg.jpg` / `.png` / `.webp`)"
    )
    c1, c2 = st.columns(2)
    with c1:
        st.write("**Face**")
        if status["face"]:
            st.image(status["face"], use_container_width=True)
            st.caption(status["face"])
        else:
            st.error("Chưa có face.*")
    with c2:
        st.write("**Background**")
        if status["bg"]:
            st.image(status["bg"], use_container_width=True)
            st.caption(status["bg"])
        else:
            st.error("Chưa có background.*")

    if not status["ok"]:
        st.markdown(
            f'<div class="warn">Thiếu ảnh trong <code>{ASSETS_DIR}</code>. '
            f"Copy face + background vào đó rồi reload trang.</div>",
            unsafe_allow_html=True,
        )

with tab_new:
    if not status["ok"]:
        st.markdown(
            f'<div class="warn">Cần face + background trong '
            f"<code>{ASSETS_DIR}</code> trước (xem tab Ảnh cố định).</div>",
            unsafe_allow_html=True,
        )

    st.subheader("1. Link TikTok")
    tiktok_url = st.text_input(
        "URL TikTok",
        placeholder="https://www.tiktok.com/@user/video/...  hoặc  https://vm.tiktok.com/...",
        label_visibility="collapsed",
    )

    with st.expander("Tuỳ chọn"):
        at = st.number_input(
            "Timestamp frame (giây, -1 = tự chọn ~35%)",
            min_value=-1.0,
            max_value=3600.0,
            value=-1.0,
            step=0.1,
        )
        skip_face = st.checkbox("Bỏ qua face swap local", value=False)
        skip_bg = st.checkbox("Bỏ qua đổi nền local", value=False)
        custom_id = st.text_input(
            "Tên run (tuỳ chọn)",
            placeholder="để trống = run_YYYYMMDD_HHMMSS",
        )

    url_ok = bool(tiktok_url.strip()) and is_tiktok_url(tiktok_url.strip())
    ready = status["ok"] and url_ok
    run_btn = st.button(
        "🚀 Tải TikTok + chuẩn bị run",
        type="primary",
        disabled=not ready,
    )

    if tiktok_url.strip() and not is_tiktok_url(tiktok_url.strip()):
        st.warning("URL không giống link TikTok.")

    if not ready and status["ok"]:
        st.markdown(
            '<div class="hint">Dán link TikTok (www / vm / vt.tiktok.com) rồi bấm chạy.</div>',
            unsafe_allow_html=True,
        )

    if run_btn and ready:
        rid = custom_id.strip() or new_run_id()
        at_val = None if at < 0 else float(at)
        with st.spinner("Đang tải TikTok (SnapTik → TikWM → yt-dlp) + chuẩn bị run…"):
            try:
                result = prepare_from_tiktok_url(
                    tiktok_url.strip(),
                    run_id=rid,
                    at=at_val,
                    skip_face=skip_face,
                    skip_bg=skip_bg,
                )
                st.session_state["last_result"] = result
            except Exception as exc:  # noqa: BLE001
                st.error(f"Lỗi: {exc}")
                result = None

        if result:
            st.success("Xong phần local. Copy tin nhắn gửi Grok.")
            st.markdown(
                f'<div class="ok"><b>Run:</b> {result["run_id"]}<br/>'
                f'<b>Source:</b> {result.get("source_url") or "—"}<br/>'
                f'<b>Thư mục:</b> <code>{result["out_dir"]}</code><br/>'
                f'<b>Style:</b> {result["style_name"]}<br/>'
                f'<b>Audio:</b> {result["audio_seconds"]:.1f}s · '
                f'shots {result["shot_durations"]}</div>',
                unsafe_allow_html=True,
            )

            st.subheader("2. Preview hero (local draft)")
            hero_path = Path(result["hero"])
            if hero_path.is_file():
                st.image(str(hero_path), use_container_width=True)
                st.warning(
                    "Đây là **bản nháp local** (OpenCV dán mặt + rembg). "
                    "Mặt lệch / viền cứng là bình thường. "
                    "Khi nhắn Grok *làm tiếp*, Grok sẽ refine → "
                    "`hero_refined.jpg` rồi mới animate."
                )

            st.subheader("3. Nhắn Grok")
            msg = result["grok_message"]
            st.code(msg, language=None)
            st.download_button(
                "Tải GROK.txt",
                data=msg + "\n",
                file_name="GROK.txt",
                mime="text/plain",
            )

            prompts_md = Path(result["prompts_md"])
            if prompts_md.is_file():
                with st.expander("Xem animate_prompts.md"):
                    st.markdown(prompts_md.read_text(encoding="utf-8"))

            st.info(
                "Trong chat Grok, dán tin nhắn trên hoặc gõ: "
                f"`làm tiếp {result['run_id']}`"
            )

with tab_latest:
    st.subheader("Run gần nhất")
    latest = read_latest()
    if not latest:
        st.write("Chưa có run. Tạo ở tab **Tạo run (TikTok)**.")
    else:
        st.json(latest)
        st.code(latest.get("grok_message", ""), language=None)
        out = Path(latest.get("out_dir", ""))
        hero = out / "hero.jpg"
        if hero.is_file():
            st.image(str(hero), caption="hero.jpg", use_container_width=True)
        st.caption(f"Pointer: `{LATEST_POINTER}` · work: `{WORK_ROOT}`")

st.divider()
st.caption(
    f"Assets: `{ASSETS_DIR}` · Project: `{ROOT}` · "
    f"Finals: `{FINAL_OUTPUTS_DIR}\\<run_id>.mp4`"
)
