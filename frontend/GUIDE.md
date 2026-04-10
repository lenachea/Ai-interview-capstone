# PreView 프론트엔드 개발 가이드

---

## 목차

1. [프로그램 개요](#1-프로그램-개요)
2. [실행 방법](#2-실행-방법)
3. [파일 구조와 수정 방법](#3-파일-구조와-수정-방법)
4. [백엔드 연결 방법](#4-백엔드-연결-방법)
5. [데스크톱 앱(Electron)으로 전환하는 방법](#5-데스크톱-앱electron으로-전환하는-방법)

---

## 1. 프로그램 개요

**PreView**는 모의면접 분석 웹 프로그램입니다.  
React 18 + Vite 기반으로 작성되었으며, 6개의 화면으로 구성됩니다.

| 화면 | URL | 설명 |
|------|-----|------|
| 메인 | `/` | 시작 화면. 두 기능 선택 버튼 |
| 장치 확인 | `/realtime` | 웹캠·마이크 권한 확인, 실시간 볼륨 시각화 |
| 영상 업로드 | `/upload` | 분석할 영상 파일 선택 (드래그&드롭) |
| 분석 중 | `/loading` | 분석 진행 로딩 화면 |
| 결과 요약 | `/results` | 육각형 레이더 차트 + 항목별 점수 |
| 상세 결과 | `/results/detail` | 좌측 레이더 고정 + 우측 표정/자세/말하기 상세 분석 |

### 기술 스택

| 항목 | 사용 기술 |
|------|-----------|
| UI 프레임워크 | React 18 |
| 빌드 도구 | Vite 5 |
| 라우팅 | React Router v6 |
| 차트 | Chart.js 4 + react-chartjs-2 |
| 스타일 | CSS Modules |
| 웹캠/마이크 | Web API (`getUserMedia`) |
| 볼륨 시각화 | Web Audio API + Canvas |

---

## 2. 실행 방법

### 사전 준비

[Node.js LTS](https://nodejs.org/) 를 설치합니다. (v18 이상 권장)

### 실행

```bash
# 1. 프로젝트 폴더로 이동
cd "C:\Users\gyeon\Desktop\한밭대\2026캡스톤\Cap_Frontend"

# 2. 패키지 설치 (최초 1회)
npm install

# 3. 개발 서버 시작
npm run dev
```

브라우저에서 `http://localhost:5173` 접속

### 배포용 빌드

```bash
npm run build
# dist/ 폴더에 정적 파일 생성됨
```

---

## 3. 파일 구조와 수정 방법

```
Cap_Frontend/
├── index.html                      ← 브라우저 탭 제목, 폰트 링크
├── vite.config.js                  ← 빌드 설정 (포트 변경 등)
├── package.json                    ← 의존성 목록
└── src/
    ├── main.jsx                    ← 앱 진입점 (건드릴 일 없음)
    ├── App.jsx                     ← 라우팅 설정
    ├── pages/                      ← 각 화면
    │   ├── Home.jsx
    │   ├── RealtimeSetup.jsx
    │   ├── VideoUpload.jsx
    │   ├── AnalysisLoading.jsx
    │   ├── ResultsOverview.jsx
    │   └── ResultsDetail.jsx
    ├── components/                 ← 재사용 컴포넌트
    │   ├── RadarChart.jsx
    │   ├── AppLogo.jsx             ← 각 페이지 상단 고정 로고
    │   └── DeviceStatusCard.jsx
    └── styles/                     ← 각 파일에 대응하는 CSS
        ├── global.css              ← 전역 색상 변수, 폰트
        ├── Home.module.css
        ├── RealtimeSetup.module.css
        └── ...
```

### 자주 수정하게 될 항목별 안내

#### 🌐 브라우저 탭 제목·폰트·파비콘 변경 (`index.html`)

프로젝트 루트의 `index.html` 파일이 앱의 HTML 진입점입니다.

```html
<!DOCTYPE html>
<html lang="ko">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />

    <!-- ① 브라우저 탭에 표시되는 제목 -->
    <title>PreView - 모의면접 분석프로그램</title>

    <!-- ② 파비콘 (탭 아이콘) — public/ 폴더에 favicon.ico 넣고 아래 줄 추가 -->
    <!-- <link rel="icon" type="image/x-icon" href="/favicon.ico" /> -->

    <!-- ③ Google Fonts (Noto Sans KR) — 인터넷 연결 없으면 시스템 폰트로 대체됨 -->
    <link rel="preconnect" href="https://fonts.googleapis.com" />
    <link
      href="https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@400;500;600;700&display=swap"
      rel="stylesheet"
    />
  </head>
  <body>
    <div id="root"></div>
    <script type="module" src="/src/main.jsx"></script>
  </body>
</html>
```

**자주 변경하는 항목:**

| 항목 | 수정 위치 |
|------|-----------|
| 탭 제목 | `<title>` 태그 안의 텍스트 |
| 파비콘 | `public/favicon.ico` 파일 추가 + 주석 해제 |
| 기본 폰트 | `href="https://fonts.googleapis.com/..."` URL에서 `family=` 파라미터 변경, `global.css`의 `--font-main`도 함께 수정 |
| 오프라인 폰트 | Google Fonts `<link>` 줄 삭제 → `public/fonts/` 에 폰트 파일 추가 → `global.css`에서 `@font-face` 선언 |

---

#### 💬 면접 준비 안내 문구 수정

`src/pages/RealtimeSetup.jsx` 파일 상단의 `GUIDANCE_ITEMS` 배열을 수정합니다.  
각 항목은 `{ icon, title, tips }` 구조이며, `tips`는 문자열 배열입니다.

```jsx
// src/pages/RealtimeSetup.jsx (파일 상단)
const GUIDANCE_ITEMS = [
  {
    icon: '📷',          // 이모지 아이콘
    title: '카메라 위치', // 소제목
    tips: [              // 세부 안내 문구 (개수 자유롭게 추가/삭제 가능)
      '카메라를 눈높이에 맞춰 정면으로 향하게 해주세요.',
      '얼굴 전체가 화면 중앙에 잘 보이도록 거리를 조절하세요.',
      '배경은 단색의 밝은 벽이나 커튼이 적합합니다.',
    ],
  },
  // ... 더 추가하거나 삭제 가능
]
```

- **항목 추가**: 배열에 `{ icon, title, tips }` 객체를 하나 더 추가
- **항목 삭제**: 해당 객체 줄을 배열에서 제거
- **문구 수정**: 원하는 `tips` 배열 안의 문자열 교체

---

#### 🎨 색상 변경

`src/styles/global.css` 파일을 열어 CSS 변수를 수정합니다.

```css
:root {
  --color-blue:  #5BB8F5;   /* 실시간 모의면접 버튼 색 */
  --color-green: #50eba0;   /* 영상 분석 버튼 색 */
}
```

#### 🖼️ 로고 교체

1. `public/` 폴더에 새 로고 이미지를 넣습니다. 파일명을 `logo.png`로 맞추면 기존 코드 그대로 동작합니다.  
   파일명을 다르게 쓰려면 `Home.jsx`, `AppLogo.jsx`, `ResultsDetail.jsx` 세 파일의 `src="/logo.png"` 부분을 일괄 수정합니다.

#### 📐 로고 크기 변경

| 위치 | 수정 파일 | 수정할 값 |
|------|-----------|-----------|
| 메인 화면 중앙 로고 | `src/styles/Home.module.css` | `.logoImg { height: 120px }` |
| 다른 화면 좌측 상단 고정 로고 | `src/styles/AppLogo.module.css` | `.logo { height: 44px }` |
| 상세결과 좌측 패널 로고 | `src/pages/ResultsDetail.jsx` 내 `PanelLogo` 함수 | `style={{ height: 40 }}` |

#### 🔲 메인 버튼 크기 변경

`src/styles/Home.module.css` 파일을 수정합니다.

```css
/* 버튼 전체 크기 */
.navBtn {
  width: 240px;   /* ← 가로 */
  height: 260px;  /* ← 세로 */
}

/* 아이콘 크기 */
.btnIcon {
  width: 90px;
  height: 90px;
}

/* 텍스트 크기 */
.btnLabel {
  font-size: 17px;
}
```

#### 📊 레이더 차트 항목 변경

`src/components/RadarChart.jsx` 파일의 `labels` 배열을 수정합니다.

```jsx
const labels = ['표정 안정성', '표정 다양성', '자세 안정성', '시선 처리', '발화 속도', '말하기 명확성']
```

항목 수를 바꾸면 `ResultsOverview.jsx`와 `ResultsDetail.jsx`의 `MOCK_SCORES` 키도 함께 수정해야 합니다.

#### 📄 결과 화면의 목업 데이터 교체

백엔드를 연결하기 전까지는 `ResultsOverview.jsx`와 `ResultsDetail.jsx` 파일 상단의 `MOCK_SCORES` / `MOCK` 객체에 임시 데이터가 들어 있습니다. 이 값을 직접 수정해서 UI를 테스트할 수 있습니다.

#### ➕ 새 화면 추가

1. `src/pages/` 폴더에 새 JSX 파일을 만듭니다. (예: `Interview.jsx`)
2. `src/styles/` 폴더에 대응하는 CSS 파일을 만듭니다. (예: `Interview.module.css`)
3. `src/App.jsx`에 라우트를 등록합니다.

```jsx
import Interview from './pages/Interview'
// ...
<Route path="/interview" element={<Interview />} />
```

#### 🗑️ 화면 삭제

1. `src/App.jsx`에서 해당 `<Route>` 줄을 지웁니다.
2. `src/pages/` 에서 해당 JSX 파일을 삭제합니다.
3. `src/styles/` 에서 해당 CSS 파일을 삭제합니다.
4. 다른 파일에서 해당 페이지로 `navigate()`하는 코드가 있으면 함께 제거합니다.

#### 📦 외부 라이브러리 추가

```bash
npm install 라이브러리명
```

예: `npm install axios` (HTTP 요청용)

---

## 4. 백엔드 연결 방법

> 백엔드는 Python Flask 또는 FastAPI로 구현한다고 가정합니다.

### 4-1. 영상 업로드 → 분석 요청

`src/pages/VideoUpload.jsx`의 `onStart` 함수를 수정합니다.

**현재 코드 (목업)**
```jsx
function onStart() {
  if (!file) return
  navigate('/loading', { state: { fileName: file.name } })
}
```

**백엔드 연결 후**
```jsx
async function onStart() {
  if (!file) return
  const formData = new FormData()
  formData.append('video', file)

  navigate('/loading', { state: { fileName: file.name } })

  try {
    const res = await fetch('http://localhost:8000/api/analyze', {
      method: 'POST',
      body: formData,
    })
    const result = await res.json()
    navigate('/results', { state: { result } })
  } catch (err) {
    console.error('분석 요청 실패:', err)
  }
}
```

### 4-2. 로딩 화면에서 분석 완료 대기

`src/pages/AnalysisLoading.jsx`에서 3초 타이머 대신 폴링(polling)으로 교체합니다.

```jsx
// 현재: setTimeout으로 3초 후 이동
useEffect(() => {
  const timer = setTimeout(() => navigate('/results'), 3000)
  return () => clearTimeout(timer)
}, [])

// 변경: 백엔드에 분석 완료 여부 폴링
useEffect(() => {
  const jobId = location.state?.jobId   // 업로드 시 받은 작업 ID
  if (!jobId) { navigate('/results'); return }

  const interval = setInterval(async () => {
    const res = await fetch(`http://localhost:8000/api/status/${jobId}`)
    const data = await res.json()
    if (data.status === 'done') {
      clearInterval(interval)
      navigate('/results', { state: { result: data.result } })
    }
  }, 2000)  // 2초마다 확인

  return () => clearInterval(interval)
}, [])
```

### 4-3. 결과 화면에 API 데이터 표시

`src/pages/ResultsOverview.jsx`와 `ResultsDetail.jsx` 파일 상단의 `MOCK_SCORES` / `MOCK` 객체를 `location.state.result`로 교체합니다.

```jsx
import { useLocation } from 'react-router-dom'

export default function ResultsOverview() {
  const location = useLocation()
  // 백엔드에서 받은 결과 (없으면 목업 사용)
  const scores = location.state?.result?.scores ?? MOCK_SCORES
  // ...
}
```

### 4-4. CORS 설정 (백엔드)

프론트엔드(`localhost:5173`)에서 백엔드(`localhost:8000`)로 요청할 때 CORS 오류가 발생할 수 있습니다.

**Flask 예시**
```python
from flask_cors import CORS
app = Flask(__name__)
CORS(app, origins=["http://localhost:5173"])
```

**FastAPI 예시**
```python
from fastapi.middleware.cors import CORSMiddleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)
```

### 4-5. 실시간 모의면접 (WebSocket)

실시간 면접 기능은 WebSocket으로 구현하는 것을 권장합니다.  
`RealtimeSetup.jsx`에서 면접 시작 버튼 클릭 시:

```jsx
// 면접 시작 버튼 onClick
const ws = new WebSocket('ws://localhost:8000/ws/interview')
ws.onopen = () => ws.send(JSON.stringify({ type: 'start' }))
ws.onmessage = (e) => {
  const data = JSON.parse(e.data)
  // 실시간 피드백 처리
}
navigate('/interview', { state: { ws } })
```

---

## 5. 데스크톱 앱(Electron)으로 전환하는 방법

Electron을 사용하면 이 웹 프론트엔드를 Windows/macOS/Linux 설치형 프로그램으로 배포할 수 있습니다.

### 5-1. Electron 패키지 설치

```bash
npm install --save-dev electron electron-builder concurrently wait-on
```

### 5-2. Electron 메인 프로세스 파일 생성

프로젝트 루트에 `electron/main.js` 파일을 새로 만듭니다.

```js
const { app, BrowserWindow } = require('electron')
const path = require('path')

function createWindow() {
  const win = new BrowserWindow({
    width: 1280,
    height: 800,
    webPreferences: {
      nodeIntegration: false,
      contextIsolation: true,
    },
  })

  // 개발 중에는 Vite 서버로, 빌드 후에는 dist/index.html 로드
  if (process.env.NODE_ENV === 'development') {
    win.loadURL('http://localhost:5173')
    win.webContents.openDevTools()
  } else {
    win.loadFile(path.join(__dirname, '../dist/index.html'))
  }
}

app.whenReady().then(createWindow)

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') app.quit()
})
```

### 5-3. package.json 수정

`package.json`에 아래 항목들을 추가합니다.

```json
{
  "main": "electron/main.js",
  "scripts": {
    "dev": "vite",
    "build": "vite build",
    "electron:dev": "concurrently \"vite\" \"wait-on http://localhost:5173 && electron .\"",
    "electron:build": "vite build && electron-builder"
  },
  "build": {
    "appId": "com.preview.app",
    "productName": "PreView",
    "directories": {
      "output": "release"
    },
    "win": {
      "target": "nsis",
      "icon": "public/icon.ico"
    },
    "mac": {
      "target": "dmg",
      "icon": "public/icon.icns"
    }
  }
}
```

### 5-4. Vite 빌드 설정 수정

`vite.config.js`에서 빌드 시 절대 경로 대신 상대 경로를 사용하도록 설정합니다.  
(Electron은 `file://` 프로토콜로 파일을 로드하기 때문)

```js
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  base: './',   // ← 이 줄 추가
})
```

### 5-5. 개발 모드 실행

```bash
npm run electron:dev
```

### 5-6. 설치 파일 빌드

```bash
# Windows: .exe 설치 파일 생성
npm run electron:build

# 생성 위치: release/ 폴더
```

### 5-7. 주의사항

- **웹캠/마이크**: Electron에서도 `getUserMedia`는 동작합니다. 단, 앱이 서명되지 않은 경우 macOS에서 권한 팝업이 다르게 표시될 수 있습니다.
- **백엔드 연동**: Python 백엔드를 Electron과 함께 배포하려면 `child_process.spawn`으로 백엔드 서버를 앱 시작 시 자동 실행하도록 `electron/main.js`에 추가해야 합니다.

```js
const { spawn } = require('child_process')

// 앱 시작 시 Python 백엔드 자동 실행 예시
const backend = spawn('python', ['../backend/main.py'], {
  cwd: path.join(__dirname, '..'),
})
backend.on('error', (err) => console.error('Backend error:', err))
app.on('before-quit', () => backend.kill())
```

---

## 부록: 주요 파일 한눈에 보기

| 수정하고 싶은 것 | 파일 |
|-----------------|------|
| 브라우저 탭 제목·파비콘·폰트 링크 | `index.html` |
| 색상, 폰트 전체 변경 | `src/styles/global.css` |
| 로고 이미지 교체 | `public/logo.png` 파일 교체 |
| 메인 화면 로고 크기 | `src/styles/Home.module.css` → `.logoImg { height }` |
| 다른 화면 상단 로고 크기 | `src/styles/AppLogo.module.css` → `.logo { height }` |
| 메인 버튼 크기 | `src/styles/Home.module.css` → `.navBtn { width / height }` |
| 메인 버튼 텍스트/색 | `src/pages/Home.jsx`, `src/styles/Home.module.css` |
| 면접 준비 안내 문구 | `src/pages/RealtimeSetup.jsx` → `GUIDANCE_ITEMS` 배열 |
| 웹캠/마이크 체크 화면 | `src/pages/RealtimeSetup.jsx` |
| 영상 업로드 UI | `src/pages/VideoUpload.jsx` |
| 로딩 화면 텍스트/애니메이션 | `src/pages/AnalysisLoading.jsx`, `src/styles/AnalysisLoading.module.css` |
| 레이더 차트 항목·색상 | `src/components/RadarChart.jsx` |
| 결과 점수 화면 | `src/pages/ResultsOverview.jsx` |
| 상세 분석 화면 | `src/pages/ResultsDetail.jsx` |
| 화면 라우팅 경로 추가/삭제 | `src/App.jsx` |
| 빌드 포트·경로 설정 | `vite.config.js` |
