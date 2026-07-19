#!/usr/bin/env python3
"""
Music Video Generator - FastAPI Web Server
静的HTMLを配信しつつ動画生成APIを提供する。
Railway / Render / fly.io / VPS どこでもデプロイ可能。
Cloudflare を前段のリバースプロキシとして使用可能。
"""

import shutil
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

from music_video_generator import ARTIST_NAME, DEFAULT_STYLE, generate_video

# ---------------------------------------------------------------------------
# アプリ設定
# ---------------------------------------------------------------------------
app = FastAPI(title="Music Video Generator", docs_url=None, redoc_url=None)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

JOBS_DIR = Path("jobs")
JOBS_DIR.mkdir(exist_ok=True)

JOB_TTL_SEC = 3600          # 1時間後にジョブを自動削除
MAX_WORKERS = 2             # 同時生成数上限

jobs: dict[str, dict] = {}
executor = ThreadPoolExecutor(max_workers=MAX_WORKERS)

# ---------------------------------------------------------------------------
# スタイルパラメータのマッピング
# ---------------------------------------------------------------------------
GLOW_PRESETS = {
    "pink":  [(255, 60, 180), (255, 80, 200), (255, 120, 220), (255, 180, 240)],
    "cyan":  [(0, 200, 255),  (20, 180, 255), (80, 210, 255),  (150, 230, 255)],
    "gold":  [(255, 140, 0),  (255, 160, 20), (255, 190, 60),  (255, 220, 120)],
    "green": [(0, 255, 80),   (40, 255, 100), (100, 255, 140), (180, 255, 190)],
    "white": [(200, 200, 200),(220, 220, 220),(240, 240, 240), (255, 255, 255)],
}
INTENSITY_MAP  = {"none": 0.0, "low": 0.4, "medium": 1.0, "high": 1.8}
POS_MAP        = {"upper": 0.27, "center_upper": 0.38, "center": 0.48}
SIZE_MAP       = {"xs": 0.030, "s": 0.040, "m": 0.055, "l": 0.072, "xl": 0.090}
WAVE_COLOR_MAP = {
    "white": (255, 255, 255, 200),
    "pink":  (255, 100, 200, 200),
    "cyan":  (0,   200, 255, 200),
    "gold":  (255, 190,  50, 200),
}
WAVE_HEIGHT_MAP = {"low": 0.08, "medium": 0.12, "high": 0.18}

FORMAT_CONFIG = {
    "tiktok":  ("TikTok (9:16)",    720, 1280, "vertical"),
    "youtube": ("YouTube横 (16:9)", 1280, 720, "youtube"),
    "shorts":  ("Shorts (9:16)",    720, 1280, "vertical"),
}

# ---------------------------------------------------------------------------
# ジョブ管理
# ---------------------------------------------------------------------------
def cleanup_old_jobs() -> None:
    now = time.time()
    expired = [jid for jid, j in list(jobs.items()) if now - j["created_at"] > JOB_TTL_SEC]
    for jid in expired:
        job_dir = JOBS_DIR / jid
        if job_dir.exists():
            shutil.rmtree(job_dir, ignore_errors=True)
        jobs.pop(jid, None)


def run_generation(job_id: str, audio_path: str, jacket_path: str, params: dict) -> None:
    job = jobs[job_id]
    job["status"] = "processing"

    fmt_list: list[str] = params["formats"]
    job["total"] = len(fmt_list)
    job["current"] = 0
    job["files"] = {}

    try:
        for fmt in fmt_list:
            label, w, h, mode = FORMAT_CONFIG[fmt]
            out_path = str(JOBS_DIR / job_id / f"{fmt}.mp4")
            job["current_label"] = label
            job["current_pct"] = 0

            def cb(pct: int, _fmt: str = fmt) -> None:
                job["current_pct"] = pct

            generate_video(
                audio_path, jacket_path, out_path,
                song_title=params.get("title", ""),
                artist_name=params.get("artist", ARTIST_NAME),
                width=w, height=h, mode=mode,
                progress_callback=cb,
                style_params=params.get("style"),
            )
            job["files"][fmt] = out_path
            job["current"] += 1

        job["status"] = "done"

    except Exception as exc:
        job["status"] = "error"
        job["error"] = str(exc)


# ---------------------------------------------------------------------------
# API エンドポイント
# ---------------------------------------------------------------------------
@app.post("/api/generate")
async def api_generate(
    audio: UploadFile = File(...),
    jacket: UploadFile = File(...),
    title: str = Form(""),
    artist: str = Form(ARTIST_NAME),
    formats: str = Form("tiktok,youtube,shorts"),
    glow_preset: str = Form("pink"),
    glow_intensity: str = Form("medium"),
    title_position: str = Form("upper"),
    font_size: str = Form("m"),
    wave_color: str = Form("white"),
    wave_height: str = Form("medium"),
):
    cleanup_old_jobs()

    job_id = str(uuid.uuid4())
    job_dir = JOBS_DIR / job_id
    job_dir.mkdir()

    # アップロードファイルを拡張子だけ保持した安全な名前で保存
    # （日本語・特殊文字を含むファイル名でも ffmpeg が確実に読める）
    audio_ext = Path(audio.filename).suffix.lower() if audio.filename else ".mp3"
    jacket_ext = Path(jacket.filename).suffix.lower() if jacket.filename else ".jpg"
    audio_path = str(job_dir / f"audio{audio_ext}")
    jacket_path = str(job_dir / f"jacket{jacket_ext}")
    with open(audio_path, "wb") as f:
        f.write(await audio.read())
    with open(jacket_path, "wb") as f:
        f.write(await jacket.read())

    fmt_list = [
        f.strip() for f in formats.split(",")
        if f.strip() in FORMAT_CONFIG
    ]
    if not fmt_list:
        raise HTTPException(400, "有効なフォーマットを指定してください")

    style_params = {
        "glow_colors":       GLOW_PRESETS.get(glow_preset, GLOW_PRESETS["pink"]),
        "glow_intensity":    INTENSITY_MAP.get(glow_intensity, 1.0),
        "title_y_ratio":     POS_MAP.get(title_position, 0.27),
        "font_size_ratio":   SIZE_MAP.get(font_size, 0.055),
        "wave_color":        WAVE_COLOR_MAP.get(wave_color, (255, 255, 255, 200)),
        "wave_height_ratio": WAVE_HEIGHT_MAP.get(wave_height, 0.12),
    }

    params = {
        "title": title,
        "artist": artist or ARTIST_NAME,
        "formats": fmt_list,
        "style": style_params,
    }

    jobs[job_id] = {
        "status": "pending",
        "created_at": time.time(),
        "current": 0,
        "total": len(fmt_list),
        "current_label": "",
        "current_pct": 0,
        "files": {},
        "error": None,
    }

    executor.submit(run_generation, job_id, audio_path, jacket_path, params)
    return {"job_id": job_id}


@app.get("/api/status/{job_id}")
def api_status(job_id: str):
    if job_id not in jobs:
        raise HTTPException(404, "Job not found")
    j = jobs[job_id]
    return {
        "status":        j["status"],
        "current":       j["current"],
        "total":         j["total"],
        "current_label": j.get("current_label", ""),
        "current_pct":   j.get("current_pct", 0),
        "formats":       list(j["files"].keys()) if j["status"] == "done" else [],
        "error":         j.get("error"),
    }


@app.get("/api/download/{job_id}/{fmt}")
def api_download(job_id: str, fmt: str):
    if job_id not in jobs:
        raise HTTPException(404, "Job not found")
    j = jobs[job_id]
    if j["status"] != "done":
        raise HTTPException(400, "Job not complete")
    if fmt not in j["files"]:
        raise HTTPException(404, "Format not found")
    filename_map = {
        "tiktok":  "tiktok_9x16.mp4",
        "youtube": "youtube_16x9.mp4",
        "shorts":  "shorts_9x16.mp4",
    }
    return FileResponse(
        j["files"][fmt],
        media_type="video/mp4",
        filename=filename_map.get(fmt, f"{fmt}.mp4"),
    )


# ---------------------------------------------------------------------------
# 静的ファイル (フロントエンド)
# ---------------------------------------------------------------------------
app.mount("/", StaticFiles(directory="static", html=True), name="static")
