FROM python:3.11-slim

# ffmpeg をインストール
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    fonts-noto-cjk \
  && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# 依存パッケージを先にインストール（レイヤーキャッシュ活用）
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# アプリをコピー
COPY music_video_generator.py .
COPY api.py .
COPY static/ ./static/

# ジョブ出力ディレクトリ
RUN mkdir -p /app/jobs

EXPOSE 8000

CMD ["uvicorn", "api:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
