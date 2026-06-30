# GPU 사용 시 nvidia/cuda 베이스. CPU만 쓸 경우 FROM python:3.10-slim 으로 교체.
FROM nvidia/cuda:12.1.1-cudnn8-runtime-ubuntu22.04

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1

# Python, ffmpeg(moviepy), JDK(konlpy) 설치
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3.10 python3-pip ffmpeg openjdk-21-jdk-headless git \
    && rm -rf /var/lib/apt/lists/*
RUN ln -sf /usr/bin/python3.10 /usr/bin/python

ENV JAVA_HOME=/usr/lib/jvm/java-21-openjdk-amd64

WORKDIR /app

# 의존성 먼저 설치 (캐시 활용)
COPY backend/requirements.txt /app/backend/requirements.txt
RUN pip install --no-cache-dir -r /app/backend/requirements.txt \
    && pip install --no-cache-dir "moviepy==1.0.3" librosa konlpy Pillow \
    && pip install --no-cache-dir torch torchaudio --index-url https://download.pytorch.org/whl/cu121 \
    && pip install --no-cache-dir faster-whisper openai python-dotenv pyannote.audio

# 전체 프로젝트 복사 (backend가 ../verbal_module, ../nonverbal_module 을 상대경로로 참조하므로 구조 유지)
COPY backend/ /app/backend/
COPY verbal_module/ /app/verbal_module/
COPY nonverbal_module/ /app/nonverbal_module/

WORKDIR /app/backend
EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
