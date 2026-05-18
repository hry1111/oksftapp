#!/usr/bin/env python3
"""
Music Video Generator - Streamlit Web UI
スマホ / タブレットブラウザから操作できる動画生成インターフェース。
"""

import io
import os
import tempfile
from pathlib import Path

import streamlit as st

# ページ設定（モバイル優先）
st.set_page_config(
    page_title="Music Video Generator",
    page_icon="🎵",
    layout="centered",
    initial_sidebar_state="collapsed",
)

# ---------------------------------------------------------------------------
# カスタムCSS (スマホ向け大きめボタン & スッキリレイアウト)
# ---------------------------------------------------------------------------
st.markdown("""
<style>
  .stButton > button { font-size: 1.1rem; padding: 0.7rem 1.2rem; width: 100%; }
  .stDownloadButton > button { font-size: 1.1rem; padding: 0.7rem 1.2rem; width: 100%; }
  .stTextInput input { font-size: 1rem; }
  .stSelectbox select { font-size: 1rem; }
  section[data-testid="stSidebar"] { display: none; }
  .block-container { padding-top: 1.5rem; padding-bottom: 2rem; }
  h1 { font-size: 1.6rem !important; }
</style>
""", unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# インポート (ffmpeg チェック込み)
# ---------------------------------------------------------------------------
try:
    import subprocess
    result = subprocess.run(["ffmpeg", "-version"], capture_output=True)
    ffmpeg_ok = result.returncode == 0
except FileNotFoundError:
    ffmpeg_ok = False

try:
    from music_video_generator import ARTIST_NAME, FPS, generate_video
    core_ok = True
except ImportError as e:
    core_ok = False
    import_error = str(e)

# ---------------------------------------------------------------------------
# ヘッダー
# ---------------------------------------------------------------------------
st.title("🎵 Music Video Generator")
st.caption("七。のAI創作屋 — 音楽 × ジャケット画像 → 動画を自動生成")

if not ffmpeg_ok:
    st.error("⚠️ ffmpeg が見つかりません。サーバーに ffmpeg をインストールしてください。")
    st.stop()
if not core_ok:
    st.error(f"⚠️ コアモジュールの読み込みに失敗しました: {import_error}")
    st.stop()

st.divider()

# ---------------------------------------------------------------------------
# Step 1: ファイルアップロード
# ---------------------------------------------------------------------------
st.subheader("① ファイルをアップロード")

col_a, col_j = st.columns(2)
with col_a:
    audio_file = st.file_uploader("🎵 音楽ファイル", type=["mp3", "wav"], label_visibility="collapsed",
                                   help="MP3 または WAV")
    st.caption("🎵 音楽ファイル (mp3 / wav)")
with col_j:
    jacket_file = st.file_uploader("🖼 ジャケット画像", type=["jpg", "jpeg", "png"], label_visibility="collapsed",
                                    help="JPG または PNG")
    st.caption("🖼 ジャケット画像 (jpg / png)")

# ジャケットプレビュー
if jacket_file:
    st.image(jacket_file, use_container_width=True, caption="ジャケットプレビュー")

st.divider()

# ---------------------------------------------------------------------------
# Step 2: テキスト設定
# ---------------------------------------------------------------------------
st.subheader("② テキスト設定")

song_title = st.text_input("曲タイトル（ネオングロー表示）", placeholder="例: 君にトリップ",
                            help="空白にするとタイトルは表示されません。")
artist_name = st.text_input("アーティスト名（左上に表示）", value=ARTIST_NAME)

st.divider()

# ---------------------------------------------------------------------------
# Step 3: スタイル設定
# ---------------------------------------------------------------------------
st.subheader("③ タイトルスタイル")

col_gc, col_gs = st.columns(2)
with col_gc:
    glow_preset = st.selectbox(
        "グローカラー",
        options=["ピンク/マゼンタ（デフォルト）", "シアン/ブルー", "ゴールド/オレンジ", "グリーン/ライム", "ホワイト（グローなし）"],
        help="タイトル文字のネオングロー色を選択"
    )
with col_gs:
    glow_intensity = st.select_slider(
        "グロー強度",
        options=["なし", "弱", "中", "強"],
        value="中",
    )

# グロー設定マッピング
GLOW_PRESETS = {
    "ピンク/マゼンタ（デフォルト）": [(255, 60, 180), (255, 80, 200), (255, 120, 220), (255, 180, 240)],
    "シアン/ブルー":                  [(0, 200, 255), (20, 180, 255), (80, 210, 255), (150, 230, 255)],
    "ゴールド/オレンジ":              [(255, 140, 0), (255, 160, 20), (255, 190, 60), (255, 220, 120)],
    "グリーン/ライム":                 [(0, 255, 80), (40, 255, 100), (100, 255, 140), (180, 255, 190)],
    "ホワイト（グローなし）":         [(200, 200, 200), (220, 220, 220), (240, 240, 240), (255, 255, 255)],
}
GLOW_INTENSITY_MAP = {"なし": 0, "弱": 0.4, "中": 1.0, "強": 1.8}

col_tp, col_ts = st.columns(2)
with col_tp:
    title_position = st.selectbox(
        "タイトル位置",
        options=["上 (27%)", "中央上 (38%)", "中央 (48%)"],
        index=0,
        help="画面上端からの距離（高さに対する割合）"
    )
with col_ts:
    font_size_override = st.select_slider(
        "フォントサイズ",
        options=["極小", "小", "中", "大", "極大"],
        value="中",
        help="タイトルの文字サイズ（自動調整あり）"
    )

TITLE_POS_MAP = {"上 (27%)": 0.27, "中央上 (38%)": 0.38, "中央 (48%)": 0.48}
FONT_SIZE_RATIO = {"極小": 0.030, "小": 0.040, "中": 0.055, "大": 0.072, "極大": 0.090}

st.divider()

# ---------------------------------------------------------------------------
# Step 4: 波形スタイル
# ---------------------------------------------------------------------------
st.subheader("④ 波形スタイル")

col_wc, col_wh = st.columns(2)
with col_wc:
    wave_color = st.selectbox(
        "波形カラー",
        options=["ホワイト（デフォルト）", "ピンク", "シアン", "ゴールド"],
    )
with col_wh:
    wave_height = st.select_slider(
        "波形の高さ",
        options=["低", "中", "高"],
        value="中",
    )

WAVE_COLOR_MAP = {
    "ホワイト（デフォルト）": (255, 255, 255, 200),
    "ピンク":                  (255, 100, 200, 200),
    "シアン":                  (0, 200, 255, 200),
    "ゴールド":                (255, 190, 50, 200),
}
WAVE_HEIGHT_MAP = {"低": 0.08, "中": 0.12, "高": 0.18}

st.divider()

# ---------------------------------------------------------------------------
# Step 5: 出力フォーマット選択
# ---------------------------------------------------------------------------
st.subheader("⑤ 出力フォーマット")

col_t, col_y, col_s = st.columns(3)
with col_t:
    do_tiktok = st.checkbox("TikTok\n9:16", value=True)
with col_y:
    do_youtube = st.checkbox("YouTube\n16:9", value=True)
with col_s:
    do_shorts = st.checkbox("Shorts\n9:16", value=True)

st.divider()

# ---------------------------------------------------------------------------
# 生成ボタン
# ---------------------------------------------------------------------------
generate_btn = st.button("▶ 動画を生成する", type="primary", use_container_width=True)

# ---------------------------------------------------------------------------
# 生成処理
# ---------------------------------------------------------------------------
if generate_btn:
    errors = []
    if not audio_file:
        errors.append("音楽ファイルをアップロードしてください。")
    if not jacket_file:
        errors.append("ジャケット画像をアップロードしてください。")
    if not (do_tiktok or do_youtube or do_shorts):
        errors.append("出力フォーマットを1つ以上選択してください。")

    for e in errors:
        st.error(e)

    if not errors:
        # スタイルパラメータをまとめる
        style_params = {
            "glow_colors": GLOW_PRESETS[glow_preset],
            "glow_intensity": GLOW_INTENSITY_MAP[glow_intensity],
            "title_y_ratio": TITLE_POS_MAP[title_position],
            "font_size_ratio": FONT_SIZE_RATIO[font_size_override],
            "wave_color": WAVE_COLOR_MAP[wave_color],
            "wave_height_ratio": WAVE_HEIGHT_MAP[wave_height],
        }

        with tempfile.TemporaryDirectory() as tmp:
            # アップロードファイルを保存
            audio_path = os.path.join(tmp, audio_file.name)
            jacket_path = os.path.join(tmp, jacket_file.name)
            with open(audio_path, "wb") as f:
                f.write(audio_file.getbuffer())
            with open(jacket_path, "wb") as f:
                f.write(jacket_file.getbuffer())

            stem = Path(audio_file.name).stem
            tasks = []
            if do_tiktok:
                tasks.append(("TikTok (9:16)", 1080, 1920, "vertical", f"{stem}_tiktok.mp4"))
            if do_youtube:
                tasks.append(("YouTube横 (16:9)", 1920, 1080, "youtube", f"{stem}_youtube.mp4"))
            if do_shorts:
                tasks.append(("Shorts (9:16)", 1080, 1920, "vertical", f"{stem}_shorts.mp4"))

            results = []
            overall = st.progress(0, text="生成を開始しています...")

            for t_idx, (label, w, h, mode, filename) in enumerate(tasks):
                out_path = os.path.join(tmp, filename)

                st.write(f"**{label}** を生成中...")
                bar = st.progress(0)
                status_txt = st.empty()

                def make_cb(b, s, t_i, n_tasks, lbl):
                    def cb(pct):
                        b.progress(pct)
                        s.caption(f"{lbl}: {pct}%")
                        overall_pct = int((t_i + pct / 100) / n_tasks * 100)
                        overall.progress(overall_pct, text=f"全体: {overall_pct}%")
                    return cb

                generate_video(
                    audio_path, jacket_path, out_path,
                    song_title=song_title,
                    artist_name=artist_name or ARTIST_NAME,
                    width=w, height=h, mode=mode,
                    progress_callback=make_cb(bar, status_txt, t_idx, len(tasks), label),
                    style_params=style_params,
                )

                bar.progress(100)
                status_txt.success(f"{label} 完了!")

                with open(out_path, "rb") as f:
                    video_bytes = f.read()
                size_mb = len(video_bytes) / 1024 / 1024
                results.append((label, video_bytes, filename, size_mb))

            overall.progress(100, text="✅ すべて完了!")

            # ダウンロードボタン
            st.divider()
            st.subheader("⬇ ダウンロード")
            for label, data, filename, size_mb in results:
                st.download_button(
                    label=f"⬇ {label}  ({size_mb:.1f} MB)",
                    data=data,
                    file_name=filename,
                    mime="video/mp4",
                    use_container_width=True,
                )

# ---------------------------------------------------------------------------
# フッター
# ---------------------------------------------------------------------------
st.divider()
st.caption("七。のAI創作屋 — Powered by Python / ffmpeg / librosa / Pillow / Streamlit")
