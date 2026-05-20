#!/usr/bin/env python3
"""
Music Video Generator - Core Library v2
音楽ファイルとジャケット画像から動画を生成するコアモジュール。
CLI と Streamlit Web アプリの両方から利用可能。
"""

import math
import os
import subprocess
import threading
from pathlib import Path
from typing import Callable, Optional

import librosa
import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

# ---------------------------------------------------------------------------
# 定数
# ---------------------------------------------------------------------------
ARTIST_NAME = "七。のAI創作屋"
AI_LABEL = "AI generated"
FPS = 30

TEXT_PADDING = 44
FONT_SIZE_AI = 24
FONT_SIZE_ARTIST = 30

WAVEFORM_SMOOTH = 5
WAVEFORM_BAR_W = 3
WAVEFORM_BAR_GAP = 2

# デフォルトスタイル設定
DEFAULT_STYLE = {
    "glow_colors": [(255, 60, 180), (255, 80, 200), (255, 120, 220), (255, 180, 240)],
    "glow_intensity": 1.0,
    "title_y_ratio": 0.27,
    "font_size_ratio": 0.055,
    "wave_color": (255, 255, 255, 200),
    "wave_height_ratio": 0.12,
}


# ---------------------------------------------------------------------------
# フォント
# ---------------------------------------------------------------------------
def get_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    candidates = [
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/opentype/noto/NotoSerifCJK-Regular.ttc",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ]
    for p in candidates:
        if os.path.exists(p):
            return ImageFont.truetype(p, size)
    return ImageFont.load_default()


# ---------------------------------------------------------------------------
# 画像ユーティリティ
# ---------------------------------------------------------------------------
def load_cover(path: str, w: int, h: int) -> Image.Image:
    """アスペクト比を維持しながらクロップして指定サイズのRGBA画像を返す。"""
    img = Image.open(path).convert("RGBA")
    iw, ih = img.size
    scale = max(w / iw, h / ih)
    new_w, new_h = int(iw * scale), int(ih * scale)
    img = img.resize((new_w, new_h), Image.LANCZOS)
    x = (new_w - w) // 2
    y = (new_h - h) // 2
    return img.crop((x, y, x + w, y + h))


def add_bottom_gradient(img: Image.Image, w: int, h: int, ratio: float = 0.45, max_alpha: int = 220) -> None:
    """下部に黒グラデーションを重ねる（in-place）。"""
    grad = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(grad)
    gh = int(h * ratio)
    for i in range(gh):
        a = int(max_alpha * (i / gh) ** 1.4)
        d.line([(0, h - gh + i), (w, h - gh + i)], fill=(0, 0, 0, a))
    img.alpha_composite(grad)


# ---------------------------------------------------------------------------
# 音声解析
# ---------------------------------------------------------------------------
def analyze_audio(audio_path: str, fps: int = FPS) -> tuple[np.ndarray, float]:
    """
    STFT で周波数パワーをフレームごとに取得する。
    Returns: (frames, duration)  frames.shape = (n_frames, freq_bins)
    """
    y, sr = librosa.load(audio_path, sr=22050, mono=True)
    duration = len(y) / sr
    hop = max(1, int(sr / fps))
    n_frames = int(duration * fps)

    stft = np.abs(librosa.stft(y, n_fft=2048, hop_length=hop))
    log_s = librosa.amplitude_to_db(stft, ref=np.max)
    log_s = (log_s - log_s.min()) / (log_s.max() - log_s.min() + 1e-8)

    cols = log_s.shape[1]
    if cols > n_frames:
        log_s = log_s[:, :n_frames]
    elif cols < n_frames:
        pad = np.zeros((log_s.shape[0], n_frames - cols))
        log_s = np.concatenate([log_s, pad], axis=1)

    return log_s.T, duration


# ---------------------------------------------------------------------------
# 描画: ネオンタイトル
# ---------------------------------------------------------------------------
def draw_neon_title(
    canvas: Image.Image,
    title: str,
    w: int,
    h: int,
    style: dict | None = None,
) -> None:
    """曲タイトルをネオングロー付きで描画する。style でカラー/サイズ/位置を変更可能。"""
    if not title:
        return

    s = {**DEFAULT_STYLE, **(style or {})}
    glow_colors = s["glow_colors"]
    intensity = s["glow_intensity"]
    y_ratio = s["title_y_ratio"]
    fs_ratio = s["font_size_ratio"]

    font_size = max(28, int(h * fs_ratio))
    font = get_font(font_size)

    dummy = ImageDraw.Draw(canvas)
    for _ in range(20):
        bb = dummy.textbbox((0, 0), title, font=font)
        if (bb[2] - bb[0]) <= w * 0.88:
            break
        font_size = max(24, font_size - 4)
        font = get_font(font_size)

    bb = dummy.textbbox((0, 0), title, font=font)
    tw, th = bb[2] - bb[0], bb[3] - bb[1]
    tx = (w - tw) // 2 - bb[0]
    ty = int(h * y_ratio)

    # グロー層: 4色 × ブラー半径 (外側→内側)
    glow_radii = [28, 16, 8, 4]
    glow_alphas = [int(90 * intensity), int(130 * intensity), int(170 * intensity), int(210 * intensity)]
    for (r, g, b), radius, alpha in zip(glow_colors, glow_radii, glow_alphas):
        if alpha <= 0:
            continue
        glow = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        gd = ImageDraw.Draw(glow)
        gd.text((tx, ty), title, font=font, fill=(r, g, b, min(255, alpha)))
        glow = glow.filter(ImageFilter.GaussianBlur(radius=radius))
        canvas.alpha_composite(glow)

    # 本文 (白 + 影)
    text_layer = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    td = ImageDraw.Draw(text_layer)
    td.text((tx + 3, ty + 3), title, font=font, fill=(0, 0, 0, 160))
    td.text((tx, ty), title, font=font, fill=(255, 255, 255, 255))
    canvas.alpha_composite(text_layer)


# ---------------------------------------------------------------------------
# 描画: ラベル (AI generated / ミニイコライザー / アーティスト名)
# ---------------------------------------------------------------------------
FADE_IN_SEC = 1.5   # フェードイン秒数
EQ_BARS = 8         # ミニイコライザーのバー数
EQ_BAR_W = 3
EQ_BAR_GAP = 2
EQ_MAX_H = 14       # バー最大高さ (px)


def draw_labels(
    canvas: Image.Image,
    artist: str,
    w: int,
    h: int,
    frame_idx: int = -1,
    frame_data: np.ndarray | None = None,
    fps: int = FPS,
) -> None:
    """
    左上に「AI generated」→ ミニイコライザー → アーティスト名を描画する。

    frame_idx >= 0 の場合:
      - 最初の FADE_IN_SEC 秒でアルファがフェードイン
      - frame_data があればミニイコライザーを音楽に連動させる
    """
    # フェードイン alpha 計算
    if frame_idx < 0:
        fade = 1.0
    else:
        fade = min(1.0, frame_idx / max(1, int(fps * FADE_IN_SEC)))

    if fade <= 0:
        return

    ov = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(ov)

    f_ai = get_font(FONT_SIZE_AI)
    f_artist = get_font(FONT_SIZE_ARTIST)
    x, y = TEXT_PADDING, TEXT_PADDING

    def st(xy, txt, font, base_fill=(255, 255, 255), base_alpha=230, shadow_alpha=150):
        fa = int(base_alpha * fade)
        sa = int(shadow_alpha * fade)
        d.text((xy[0] + 2, xy[1] + 2), txt, font=font, fill=(*[0, 0, 0], sa))
        d.text(xy, txt, font=font, fill=(*base_fill, fa))

    # ── "AI generated"
    st((x, y), AI_LABEL, f_ai, base_fill=(210, 210, 210))
    bb_ai = d.textbbox((x, y), AI_LABEL, font=f_ai)
    ai_h = bb_ai[3] - bb_ai[1]

    # ── ミニイコライザー (2行の間)
    eq_top = y + ai_h + 5
    eq_bottom = eq_top + EQ_MAX_H

    if frame_data is not None:
        n_freq = len(frame_data)
        # 低〜中周波数帯域 (最初の1/3) から取得
        upper = max(EQ_BARS, n_freq // 3)
        indices = np.linspace(0, upper - 1, EQ_BARS).astype(int)
        amps = frame_data[indices]
        # 少しランダム感のためにフレームに応じた位相シフトを加える
        phase = (frame_idx * 0.15) if frame_idx >= 0 else 0
        amps = np.clip(amps + 0.1 * np.sin(np.arange(EQ_BARS) + phase), 0, 1)
    else:
        amps = np.ones(EQ_BARS) * 0.5

    for i, amp in enumerate(amps):
        bh = max(2, int(amp * EQ_MAX_H))
        bx0 = x + i * (EQ_BAR_W + EQ_BAR_GAP)
        bx1 = bx0 + EQ_BAR_W
        by0 = eq_bottom - bh
        bar_alpha = int(190 * fade)
        d.rectangle([bx0, by0, bx1, eq_bottom], fill=(180, 180, 180, bar_alpha))

    # ── アーティスト名
    artist_y = eq_bottom + 5
    st((x, artist_y), artist, f_artist)

    canvas.alpha_composite(ov)


# ---------------------------------------------------------------------------
# 描画: ビニールレコード (スピン)
# ---------------------------------------------------------------------------
def draw_vinyl(canvas: Image.Image, frame_idx: int, w: int, h: int) -> None:
    """右下にビニールレコードを描画する（フレームごとに回転）。"""
    radius = int(min(w, h) * 0.095)
    cx = w - int(radius * 0.55)
    cy = h - int(radius * 0.55)

    ov = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(ov)

    # 外周（黒）
    d.ellipse([cx - radius, cy - radius, cx + radius, cy + radius],
              fill=(18, 18, 18, 230))

    # グルーブ（溝）
    for r in range(radius - 4, radius // 3 + 8, -7):
        d.ellipse([cx - r, cy - r, cx + r, cy + r],
                  outline=(55, 55, 55, 170), width=1)

    # センターラベル
    label_r = int(radius * 0.38)
    d.ellipse([cx - label_r, cy - label_r, cx + label_r, cy + label_r],
              fill=(28, 28, 28, 245))

    # スピン表示 (ラベル上の小さい白点が回る)
    angle = math.radians((frame_idx * 3.6) % 360)
    sr_ = label_r - 8
    ax = cx + int(sr_ * math.cos(angle))
    ay = cy + int(sr_ * math.sin(angle))
    d.ellipse([ax - 4, ay - 4, ax + 4, ay + 4], fill=(120, 120, 120, 200))

    # センターホール (ゴールド)
    dot_r = max(6, int(radius * 0.06))
    d.ellipse([cx - dot_r, cy - dot_r, cx + dot_r, cy + dot_r],
              fill=(255, 190, 40, 255))

    canvas.alpha_composite(ov)


# ---------------------------------------------------------------------------
# 描画: 波形ビジュアライザー
# ---------------------------------------------------------------------------
def draw_waveform(
    canvas: Image.Image,
    frame_data: np.ndarray,
    rx: int, ry: int, rw: int, rh: int,
    style: dict | None = None,
) -> None:
    """点線ベースライン + バーのスタイルで波形を描画する。"""
    s = {**DEFAULT_STYLE, **(style or {})}
    bar_color = s["wave_color"]  # (R, G, B, A)

    n_bars = rw // (WAVEFORM_BAR_W + WAVEFORM_BAR_GAP)
    if n_bars == 0:
        return

    idx = np.linspace(0, len(frame_data) - 1, n_bars).astype(int)
    amps = frame_data[idx]
    kernel = np.ones(WAVEFORM_SMOOTH) / WAVEFORM_SMOOTH
    amps = np.convolve(amps, kernel, mode="same")

    ov = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(ov)

    baseline_y = ry + rh

    # 点線ベースライン
    for dx in range(0, rw, 7):
        bx = rx + dx
        d.ellipse([bx, baseline_y - 1, bx + 2, baseline_y + 1],
                  fill=(*bar_color[:3], 90))

    # 波形バー（上向き）
    for i, amp in enumerate(amps):
        bar_h = max(3, int(amp * rh))
        x0 = rx + i * (WAVEFORM_BAR_W + WAVEFORM_BAR_GAP)
        x1 = x0 + WAVEFORM_BAR_W
        y0 = baseline_y - bar_h
        alpha = min(255, int(bar_color[3] * (0.7 + 0.5 * amp)))
        d.rectangle([x0, y0, x1, baseline_y], fill=(*bar_color[:3], alpha))

    canvas.alpha_composite(ov)


# ---------------------------------------------------------------------------
# ベースキャンバス構築
# ---------------------------------------------------------------------------
def build_base_vertical(
    jacket_path: str, w: int, h: int,
    song_title: str, artist: str,
    style: dict | None = None,
) -> Image.Image:
    """縦動画 (TikTok / Shorts) 用ベースキャンバス。静的要素（ジャケット・グラデ・タイトル）を事前描画済み。"""
    base = load_cover(jacket_path, w, h)
    add_bottom_gradient(base, w, h, ratio=0.42, max_alpha=215)
    draw_neon_title(base, song_title, w, h, style)
    return base


def build_base_youtube(
    jacket_path: str, w: int, h: int,
    song_title: str, artist: str,
    style: dict | None = None,
) -> Image.Image:
    """YouTube横動画 (16:9) 用ベースキャンバス。両サイドにぼかし背景。"""
    bg = Image.open(jacket_path).convert("RGBA")
    bw, bh = bg.size
    scale = max(w / bw, h / bh)
    bg = bg.resize((int(bw * scale), int(bh * scale)), Image.LANCZOS)
    cx = (bg.width - w) // 2
    cy = (bg.height - h) // 2
    bg = bg.crop((cx, cy, cx + w, cy + h))
    bg = bg.filter(ImageFilter.GaussianBlur(radius=48))

    dark = Image.new("RGBA", (w, h), (0, 0, 0, 155))
    bg.alpha_composite(dark)

    jk = Image.open(jacket_path).convert("RGBA")
    jw, jh = jk.size
    max_h = int(h * 0.90)
    max_w = int(w * 0.52)
    sc = min(max_h / jh, max_w / jw)
    new_jw, new_jh = int(jw * sc), int(jh * sc)
    jk = jk.resize((new_jw, new_jh), Image.LANCZOS)
    ox = (w - new_jw) // 2
    oy = (h - new_jh) // 2
    bg.alpha_composite(jk, (ox, oy))

    add_bottom_gradient(bg, w, h, ratio=0.35, max_alpha=185)
    draw_neon_title(bg, song_title, w, h, style)
    return bg


# ---------------------------------------------------------------------------
# 動画生成 (コア)
# ---------------------------------------------------------------------------
def generate_video(
    audio_path: str,
    jacket_path: str,
    output_path: str,
    song_title: str = "",
    artist_name: str = ARTIST_NAME,
    width: int = 1080,
    height: int = 1920,
    mode: str = "vertical",
    fps: int = FPS,
    progress_callback: Optional[Callable[[int], None]] = None,
    style_params: dict | None = None,
) -> None:
    """
    動画を1本生成してファイルに書き出す。
    progress_callback(pct: int) が各秒ごとに呼ばれる (0–100)。
    style_params で見た目をカスタマイズ可能（DEFAULT_STYLE を上書き）。
    """
    s = {**DEFAULT_STYLE, **(style_params or {})}
    frames_data, duration = analyze_audio(audio_path, fps)
    n_frames = len(frames_data)

    # 静的ベースを事前構築（フレームループ外でレンダリング済み）
    if mode == "youtube":
        base = build_base_youtube(jacket_path, width, height, song_title, artist_name, s)
    else:
        base = build_base_vertical(jacket_path, width, height, song_title, artist_name, s)

    # 波形エリア (下部)
    wf_h = int(height * s["wave_height_ratio"])
    wf_bottom = height - 28
    wf_top = wf_bottom - wf_h
    wf_x = TEXT_PADDING
    wf_w = width - TEXT_PADDING * 2

    ffmpeg_cmd = [
        "ffmpeg", "-y",
        "-f", "rawvideo", "-vcodec", "rawvideo",
        "-s", f"{width}x{height}",
        "-pix_fmt", "rgba",
        "-r", str(fps),
        "-i", "pipe:0",
        "-i", audio_path,
        "-c:v", "libx264", "-preset", "fast", "-crf", "18",
        "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "320k",
        "-shortest", "-movflags", "+faststart",
        output_path,
    ]

    # stderr をバックグラウンドスレッドで収集（バッファ詰まり防止）
    stderr_lines: list[str] = []

    def _read_stderr(pipe) -> None:
        for line in iter(pipe.readline, b""):
            stderr_lines.append(line.decode("utf-8", errors="replace").rstrip())

    with subprocess.Popen(ffmpeg_cmd, stdin=subprocess.PIPE, stderr=subprocess.PIPE) as proc:
        t = threading.Thread(target=_read_stderr, args=(proc.stderr,), daemon=True)
        t.start()

        try:
            for i, frame_data in enumerate(frames_data):
                frame = base.copy()
                draw_vinyl(frame, i, width, height)
                draw_waveform(frame, frame_data, wf_x, wf_top, wf_w, wf_h, s)
                draw_labels(frame, artist_name, width, height,
                            frame_idx=i, frame_data=frame_data, fps=fps)
                proc.stdin.write(frame.tobytes())

                if progress_callback and i % fps == 0:
                    progress_callback(int(i / n_frames * 100))

        except BrokenPipeError:
            # ffmpeg が途中で終了 → ループを抜けて returncode を確認
            pass
        finally:
            try:
                proc.stdin.close()
            except OSError:
                pass

        proc.wait()
        t.join(timeout=3)

        if proc.returncode != 0:
            err_detail = "\n".join(stderr_lines[-20:])
            raise RuntimeError(
                f"ffmpeg failed (exit {proc.returncode}) → {output_path}\n{err_detail}"
            )

    if progress_callback:
        progress_callback(100)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="音楽動画ジェネレーター (CLI)")
    parser.add_argument("audio", help="音楽ファイル (.mp3 / .wav)")
    parser.add_argument("jacket", help="ジャケット画像 (.jpg / .png)")
    parser.add_argument("--title", default="", help="曲タイトル（ネオングロー表示）")
    parser.add_argument("--artist", default=ARTIST_NAME, help="アーティスト名")
    parser.add_argument("-o", "--output-dir", default="output")
    parser.add_argument("--tiktok", action="store_true")
    parser.add_argument("--youtube", action="store_true")
    parser.add_argument("--shorts", action="store_true")
    args = parser.parse_args()

    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = Path(args.audio).stem

    gen_all = not (args.tiktok or args.youtube or args.shorts)
    tasks = []
    if gen_all or args.tiktok:
        tasks.append(("TikTok (9:16)", 1080, 1920, "vertical", out_dir / f"{stem}_tiktok.mp4"))
    if gen_all or args.youtube:
        tasks.append(("YouTube横 (16:9)", 1920, 1080, "youtube", out_dir / f"{stem}_youtube.mp4"))
    if gen_all or args.shorts:
        tasks.append(("Shorts (9:16)", 1080, 1920, "vertical", out_dir / f"{stem}_shorts.mp4"))

    print(f"\n=== Music Video Generator ===")
    print(f"  音楽: {args.audio}  /  ジャケット: {args.jacket}")
    if args.title:
        print(f"  タイトル: {args.title}")
    print()

    for idx, (label, w, h, mode, out_path) in enumerate(tasks, 1):
        print(f"[{idx}/{len(tasks)}] {label} 生成中...")

        def cb(pct, lbl=label):
            print(f"\r  {lbl}: {pct}%", end="", flush=True)

        generate_video(
            args.audio, args.jacket, str(out_path),
            song_title=args.title, artist_name=args.artist,
            width=w, height=h, mode=mode,
            progress_callback=cb,
        )
        size_mb = os.path.getsize(out_path) / 1024 / 1024
        print(f"\r  完了: {out_path} ({size_mb:.1f} MB)")

    print("\n完了!")


if __name__ == "__main__":
    main()
