#!/bin/bash
# 컨테이너가 초기화되어 패키지가 사라진 경우에만 실행 (약 5~10분)
# 버전 조합에 이유가 있음:
#   numpy 2.2.6      — 2.5.x면 mediapipe/matplotlib ABI 깨짐
#   onnxruntime-gpu 1.19.2 — 1.30은 CUDA13 요구, 이 환경은 CUDA12
#   timm 0.9.16      — 1.x면 hsemotion 체크포인트 로드 실패(conv_s2d AttributeError)
set -e

apt-get update -qq
apt-get install -y -qq default-jdk-headless libegl1 libgl1 libglib2.0-0 libgles2

pip install -q \
    faster-whisper openai-whisper librosa soundfile moviepy \
    opencv-python-headless mediapipe hsemotion "timm==0.9.16" \
    konlpy jpype1 \
    rtmlib "onnxruntime-gpu==1.19.2" "nvidia-cudnn-cu12==9.1.0.70" \
    xgboost openpyxl

pip install -q "numpy==2.2.6"   # 다른 패키지가 올려놓을 수 있으므로 마지막에 고정

echo "완료. 실행 시 아래 환경변수 필요:"
echo '  export LD_LIBRARY_PATH=/opt/conda/lib/python3.12/site-packages/nvidia/cudnn/lib:/opt/conda/lib:$LD_LIBRARY_PATH'
