# PreView — AI 면접 피드백 시스템

멀티모달 AI 기반 모의면접 분석 캡스톤 프로젝트입니다.  
면접 영상을 업로드하면 언어·비언어 측면을 자동 분석하고 종합 피드백을 제공합니다.

---

## 주요 기능

| 분류 | 항목 | 설명 |
|------|------|------|
| 언어 분석 | 음성 인식 | Whisper 기반 STT |
| 언어 분석 | 답변 품질 | 명확성·논리성·키워드 분석 |
| 언어 분석 | 필러 감지 | "음", "어" 등 불필요한 추임새 탐지 |
| 비언어 분석 | 표정 분석 | HSEmotion(enet_b2_8) — 8가지 감정 분류 |
| 비언어 분석 | 시선 분석 | MediaPipe Face Landmarker — 시선 방향 & 이탈 구간 |
| 비언어 분석 | 상반신 자세 | MediaPipe Pose — 자세 안정성 분석 |

---

## 프로젝트 구조

```
├── backend/                # FastAPI 서버
│   ├── main.py             # API 엔드포인트
│   ├── preprocessor.py     # 영상 → 오디오/프레임 분리
│   ├── scorer.py           # 점수 계산
│   └── requirements.txt
│
├── verbal_module/          # 언어 분석 모듈
│   ├── main.py
│   ├── filler_detector.py
│   ├── analyzers/
│   └── requirements.txt
│
├── nonverbal_language/     # 비언어 분석 모듈
│   ├── expresssion/
│   │   └── emotion_feature_final.py   # 표정 분석 (JSON 출력)
│   ├── eyecontact/
│   │   └── eye.py                     # 시선 분석 (JSON 출력)
│   └── face_landmarker.task           # MediaPipe 모델
│
└── Cap_Frontend/           # React 프론트엔드
    └── src/
        ├── pages/
        └── components/
```

---

## 설치 및 실행

### 1. 백엔드

```bash
cd backend
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

### 2. 언어 분석 모듈 의존성

```bash
cd verbal_module
pip install -r requirements.txt
```

> Whisper 및 torch가 포함되어 있어 GPU 환경 권장

### 3. 비언어 분석 모듈 의존성

```bash
pip install mediapipe hsemotion opencv-python scikit-learn pillow
```

### 4. 프론트엔드

```bash
cd Cap_Frontend
npm install
npm run dev
```

---

## API 엔드포인트

| Method | URL | 설명 |
|--------|-----|------|
| POST | `/analyze` | 영상 업로드 및 분석 시작 |
| GET | `/results/{job_id}` | 분석 결과 조회 |
| GET | `/history` | 완료된 분석 기록 목록 |
| GET | `/compare/{job_id}` | 현재·이전 결과 비교 |
| GET | `/audio-clip/{job_id}` | 감점 구간 오디오 클립 |

---

## 분석 결과 출력 형식

### 표정 분석 (`emotion_results.json`)
```json
{
  "accuracy": 0.82,
  "classification_report": { ... },
  "predictions": [
    { "image": "frame.jpg", "gt": 4, "pred": 4 }
  ]
}
```

### 시선 분석 (`gaze_results.json`)
```json
{
  "summary": {
    "gaze_ratio": 0.85,
    "direction_ratios": { "left": 0.05, "right": 0.03, ... },
    "feedback": "시선 처리 안정적",
    "deviated_segments": []
  },
  "gaze_log": [ ... ]
}
```

---

## 기술 스택

- **Backend**: FastAPI, Python
- **STT**: OpenAI Whisper
- **비언어 분석**: MediaPipe, HSEmotion, OpenCV
- **Frontend**: React, Vite, Chart.js
