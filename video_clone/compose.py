"""Compose hero still: new face + new background on a subject frame.

Local OpenCV face paste is a *draft preview* only. Production quality comes from
Grok image_edit refine (hero_refined.jpg) before image_to_video.
"""

from __future__ import annotations

import urllib.request
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageFilter

# OpenCV 5: FaceDetectorYN (YuNet). Also returns 5 facial landmarks.
_YUNET_URL = (
    "https://github.com/opencv/opencv_zoo/raw/main/models/"
    "face_detection_yunet/face_detection_yunet_2023mar.onnx"
)
_YUNET_NAME = "face_detection_yunet_2023mar.onnx"
_face_detector: object | None = None


def _load_bgr(path: Path) -> np.ndarray:
    img = cv2.imread(str(path), cv2.IMREAD_COLOR)
    if img is None:
        raise FileNotFoundError(f"Cannot read image: {path}")
    return img


def _load_rgb_pil(path: Path) -> Image.Image:
    return Image.open(path).convert("RGB")


def _model_cache_dir() -> Path:
    base = Path.home() / ".cache" / "video-clone-mvp"
    base.mkdir(parents=True, exist_ok=True)
    return base


def _ensure_yunet_model() -> Path:
    path = _model_cache_dir() / _YUNET_NAME
    if path.is_file() and path.stat().st_size > 100_000:
        return path
    print(f"Downloading face detector model → {path}")
    tmp = path.with_suffix(".onnx.part")
    urllib.request.urlretrieve(_YUNET_URL, tmp)
    tmp.replace(path)
    return path


def _get_yunet_detector(input_w: int, input_h: int):
    global _face_detector
    model = str(_ensure_yunet_model())
    if _face_detector is None:
        _face_detector = cv2.FaceDetectorYN_create(
            model,
            "",
            (input_w, input_h),
            0.55,
            0.3,
            5000,
        )
    else:
        _face_detector.setInputSize((input_w, input_h))
    return _face_detector


def _detect_face_full(
    bgr: np.ndarray,
) -> tuple[tuple[int, int, int, int], np.ndarray | None] | None:
    """
    Return ((x,y,w,h), landmarks_5x2 or None).
    YuNet landmarks order: right_eye, left_eye, nose, right_mouth, left_mouth.
    """
    h, w = bgr.shape[:2]
    if hasattr(cv2, "FaceDetectorYN_create"):
        try:
            detector = _get_yunet_detector(w, h)
            _retval, faces = detector.detect(bgr)
            if faces is not None and len(faces) > 0:
                best = max(faces, key=lambda f: float(f[2]) * float(f[3]))
                x, y, fw, fh = [int(v) for v in best[:4]]
                lms = np.array(
                    [
                        [best[4], best[5]],
                        [best[6], best[7]],
                        [best[8], best[9]],
                        [best[10], best[11]],
                        [best[12], best[13]],
                    ],
                    dtype=np.float32,
                )
                return (x, y, fw, fh), lms
        except Exception:
            pass

    # Haar fallback — box only
    if hasattr(cv2, "CascadeClassifier"):
        gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
        cascade_path = Path(cv2.data.haarcascades) / "haarcascade_frontalface_default.xml"
        if cascade_path.is_file():
            detector = cv2.CascadeClassifier(str(cascade_path))
            faces = detector.detectMultiScale(
                gray, scaleFactor=1.1, minNeighbors=5, minSize=(48, 48)
            )
            if len(faces) > 0:
                x, y, fw, fh = max(faces, key=lambda f: f[2] * f[3])
                return (int(x), int(y), int(fw), int(fh)), None
    return None


def _detect_largest_face(bgr: np.ndarray) -> tuple[int, int, int, int] | None:
    full = _detect_face_full(bgr)
    return full[0] if full else None


def _soft_face_mask(h: int, w: int) -> np.ndarray:
    """Taller oval covering forehead→chin with soft falloff (less 'sticker' look)."""
    mask = np.zeros((h, w), dtype=np.uint8)
    cx, cy = w // 2, int(h * 0.48)
    axes = (int(w * 0.42), int(h * 0.52))
    cv2.ellipse(mask, (cx, cy), axes, 0, 0, 360, 255, -1)
    k = max(15, (min(h, w) // 12) | 1)
    mask = cv2.GaussianBlur(mask, (k, k), 0)
    return mask


def _color_match(src: np.ndarray, ref: np.ndarray, mask: np.ndarray) -> np.ndarray:
    src_f = src.astype(np.float32)
    ref_f = ref.astype(np.float32)
    m = mask > 40
    if not np.any(m):
        return src
    out = src_f.copy()
    for c in range(3):
        s = src_f[:, :, c][m]
        r = ref_f[:, :, c][m]
        s_mean, s_std = float(s.mean()), float(s.std()) + 1e-6
        r_mean, r_std = float(r.mean()), float(r.std()) + 1e-6
        # Cap transfer so skin doesn't blow out
        scale = np.clip(r_std / s_std, 0.6, 1.5)
        channel = (src_f[:, :, c] - s_mean) * scale + r_mean
        out[:, :, c] = channel
    return np.clip(out, 0, 255).astype(np.uint8)


def _align_face_by_landmarks(
    face_bgr: np.ndarray,
    src_lms: np.ndarray,
    dst_lms: np.ndarray,
    out_shape: tuple[int, int],
) -> np.ndarray:
    """
    Similarity transform using eyes+nose (3 points) → warp source face into
    destination face geometry. out_shape = (h, w) of full frame.
    """
    # Use right eye, left eye, nose
    src = src_lms[:3].astype(np.float32)
    dst = dst_lms[:3].astype(np.float32)
    M, _ = cv2.estimateAffinePartial2D(src, dst, method=cv2.LMEDS)
    if M is None:
        # fallback: scale box
        return face_bgr
    h, w = out_shape
    warped = cv2.warpAffine(
        face_bgr,
        M,
        (w, h),
        flags=cv2.INTER_CUBIC,
        borderMode=cv2.BORDER_REFLECT_101,
    )
    return warped


def swap_face(frame_bgr: np.ndarray, face_bgr: np.ndarray) -> np.ndarray:
    """
    Landmark-aligned face paste (draft quality).

    Prefer Grok image_edit for final hero_refined.jpg.
    """
    tgt = _detect_face_full(frame_bgr)
    src = _detect_face_full(face_bgr)
    if tgt is None:
        raise RuntimeError(
            "No face detected in frame. Try another --at timestamp or a clearer frame."
        )
    if src is None:
        raise RuntimeError(
            "No face detected in face photo. Use a clear, front-facing portrait."
        )

    (tx, ty, tw, th), tgt_lms = tgt
    (sx, sy, sw, sh), src_lms = src
    fh, fw = frame_bgr.shape[:2]

    # Expand ROI around target face (jaw + forehead + a bit of hairline)
    pad_x = int(tw * 0.28)
    pad_y_top = int(th * 0.45)
    pad_y_bot = int(th * 0.35)
    x1 = max(0, tx - pad_x)
    y1 = max(0, ty - pad_y_top)
    x2 = min(fw, tx + tw + pad_x)
    y2 = min(fh, ty + th + pad_y_bot)
    roi_w, roi_h = x2 - x1, y2 - y1

    if tgt_lms is not None and src_lms is not None:
        # Warp entire source photo into frame coordinates via landmarks
        warped_full = _align_face_by_landmarks(face_bgr, src_lms, tgt_lms, (fh, fw))
        face_patch = warped_full[y1:y2, x1:x2]
        if face_patch.size == 0:
            face_patch = cv2.resize(
                face_bgr[sy : sy + sh, sx : sx + sw],
                (roi_w, roi_h),
                interpolation=cv2.INTER_CUBIC,
            )
    else:
        face_crop = face_bgr[sy : sy + sh, sx : sx + sw]
        face_patch = cv2.resize(face_crop, (roi_w, roi_h), interpolation=cv2.INTER_CUBIC)

    mask = _soft_face_mask(roi_h, roi_w)
    dest_patch = frame_bgr[y1:y2, x1:x2]
    if face_patch.shape[:2] != dest_patch.shape[:2]:
        face_patch = cv2.resize(
            face_patch, (dest_patch.shape[1], dest_patch.shape[0]), interpolation=cv2.INTER_CUBIC
        )
        mask = _soft_face_mask(dest_patch.shape[0], dest_patch.shape[1])

    face_matched = _color_match(face_patch, dest_patch, mask)

    # Seamless clone when possible
    try:
        solid = (mask > 20).astype(np.uint8) * 255
        # Erode a bit so clone focuses on face interior
        k = max(3, (min(roi_h, roi_w) // 30) | 1)
        solid = cv2.erode(solid, np.ones((k, k), np.uint8), iterations=1)
        center = (x1 + roi_w // 2, y1 + roi_h // 2)
        blended = cv2.seamlessClone(
            face_matched,
            frame_bgr,
            solid,
            center,
            cv2.NORMAL_CLONE,
        )
        # Feather edges: mix with alpha mask on top of seamless result
        alpha = (mask.astype(np.float32) / 255.0)[..., None]
        out = blended.copy()
        region = out[y1:y2, x1:x2].astype(np.float32)
        # Only lightly prefer seamless interior
        mixed = region  # already blended
        out[y1:y2, x1:x2] = np.clip(mixed, 0, 255).astype(np.uint8)
        return out
    except cv2.error:
        alpha = (mask.astype(np.float32) / 255.0)[..., None]
        out = frame_bgr.copy()
        region = out[y1:y2, x1:x2].astype(np.float32)
        mixed = face_matched.astype(np.float32) * alpha + region * (1.0 - alpha)
        out[y1:y2, x1:x2] = np.clip(mixed, 0, 255).astype(np.uint8)
        return out


def replace_background(
    subject_bgr: np.ndarray,
    bg_path: Path,
    *,
    session=None,
) -> np.ndarray:
    """Remove original background and composite onto a new background image."""
    from rembg import remove

    rgb = cv2.cvtColor(subject_bgr, cv2.COLOR_BGR2RGB)
    pil = Image.fromarray(rgb)
    cutout = remove(pil, session=session).convert("RGBA")

    # Soften matte edges (reduces halo after rembg)
    alpha = cutout.split()[-1]
    alpha = alpha.filter(ImageFilter.GaussianBlur(radius=1.2))
    cutout.putalpha(alpha)

    bg = _load_rgb_pil(bg_path)
    sw, sh = cutout.size
    bw, bh = bg.size
    scale = max(sw / bw, sh / bh)
    new_w, new_h = int(bw * scale + 0.5), int(bh * scale + 0.5)
    bg = bg.resize((new_w, new_h), Image.Resampling.LANCZOS)
    left = (new_w - sw) // 2
    top = (new_h - sh) // 2
    bg = bg.crop((left, top, left + sw, top + sh))

    composed = Image.alpha_composite(bg.convert("RGBA"), cutout)
    composed_rgb = np.array(composed.convert("RGB"))
    return cv2.cvtColor(composed_rgb, cv2.COLOR_RGB2BGR)


def compose_hero(
    frame_path: Path,
    face_path: Path,
    bg_path: Path,
    out_path: Path,
    *,
    skip_face: bool = False,
    skip_bg: bool = False,
) -> Path:
    """
    Draft hero still:
      frame → (optional face swap) → (optional bg replace) → save

    This local result is intentionally a preview. Run Grok image_edit on
    frame+face+bg to produce hero_refined.jpg for animation.
    """
    frame_path = frame_path.resolve()
    face_path = face_path.resolve()
    bg_path = bg_path.resolve()
    out_path = out_path.resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)

    img = _load_bgr(frame_path)

    if not skip_face:
        face = _load_bgr(face_path)
        img = swap_face(img, face)

    if not skip_bg:
        img = replace_background(img, bg_path)

    ok = cv2.imwrite(str(out_path), img, [int(cv2.IMWRITE_JPEG_QUALITY), 95])
    if not ok:
        raise RuntimeError(f"Failed to write hero image: {out_path}")

    # Side note for operators
    note = out_path.with_name("HERO_NOTE.txt")
    note.write_text(
        "hero.jpg is a LOCAL DRAFT (OpenCV face paste + rembg).\n"
        "Expect rough edges / face mismatch.\n"
        "For animation, use Grok image_edit → hero_refined.jpg "
        "(frame + assets/face + assets/background).\n",
        encoding="utf-8",
    )
    return out_path
