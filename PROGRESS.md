# PreView 진행 상황 정리

이 문서는 실시간 모의면접 기능 확장 작업(계획 파일: `quizzical-conjuring-sedgewick.md`)에서 실제로 구현·검증된 내용을 정리한 기록입니다.

## 1. 질문 DB 증설

- [backend/questions.py](backend/questions.py)
- `QUESTION_CATEGORIES`의 인성면접/직무역량/상황대처 각 카테고리를 3개 → 10개로 증설.
- `SESSION_QUESTION_COUNT = 3` 상수 추가 — 세션당 질문 수는 항상 3개로 고정, 10개 중 매번 무작위로 3개 선택.

## 2. 녹화 방식 전환 — 연속 녹화 + 클라이언트 타임스탬프

기존에는 질문마다 `MediaRecorder`를 멈췄다 다시 시작하며 클립을 하나씩 업로드했는데, 이를 **처음부터 끝까지 하나로 이어지는 녹화** + **"다음질문" 클릭 시점을 타임스탬프로 기록**하는 방식으로 전환.

- [Cap_Frontend/src/pages/RealtimeInterview.jsx](Cap_Frontend/src/pages/RealtimeInterview.jsx) — 녹화 시작을 최초 1회만 실행, 질문 전환 시에는 TTS만 재생. "다음질문" 클릭마다 `{index, question, start, end}` 형태로 타임스탬프 배열에 push, 마지막 질문에서 recorder를 멈추고 영상 1개 + 타임스탬프 배열을 함께 업로드.
- [Cap_Frontend/src/lib/api.js](Cap_Frontend/src/lib/api.js) — `uploadRealtimeClip` 제거, `finishRealtimeInterview(jobId, videoBlob, timestamps)`로 시그니처 변경(multipart 업로드).
- [backend/main.py](backend/main.py) — `POST /realtime/{job_id}/clip` 엔드포인트 제거. `POST /realtime/{job_id}/finish`가 영상 파일 + 타임스탬프를 받아 저장하도록 재작성. `_run_realtime_analysis`를 클립별 반복/오프셋 병합 로직 없이, 영상 전체에 대해 오디오·프레임 추출 1회 + STT 1회 후 타임스탬프 구간별로 언어 분석하는 방식으로 재작성 (`/analyze` 업로드 플로우와 동일한 구조로 단순화, Whisper 전사 호출도 클립마다가 아니라 전체 1회로 감소).
- 신규 엔드포인트 `GET /realtime/{job_id}/video` — 녹화된 영상을 그대로 스트리밍(다시보기용).

## 3. 실시간 면접 화면 레이아웃 재배치

- [Cap_Frontend/src/pages/RealtimeInterview.jsx](Cap_Frontend/src/pages/RealtimeInterview.jsx), [Cap_Frontend/src/styles/RealtimeInterview.module.css](Cap_Frontend/src/styles/RealtimeInterview.module.css)
- 사용자가 그린 와이어프레임에 맞춰 상단 질문 알약형 바(`.questionPill`) → 큰 영상 박스(`.videoWrap`, `flex:1`로 남은 공간 대부분 차지) → 우하단 "다음질문" 버튼 구조로 재구성.
- 웹캠이 가려졌을 때 텍스트 오버레이 대신 사람 실루엣 SVG placeholder 추가.
- 이후 사용자가 직접 세부 스타일(영상 박스 높이/폭, `display:block`, `aspect-ratio` 등)을 조정하며 검은 여백 이슈 등을 보완함.

## 4. 실전연습 모드

카메라 화면은 가리되 녹화는 계속되고, 질문은 무작위로 섞여서 나오며, 나중에 영상을 다시 볼 수 있고, 일반 모드(카메라를 보고 진행한 모의면접)와 점수를 비교하는 모드.

- [backend/main.py](backend/main.py) — `RealtimeStartRequest`에 `mode` 필드 추가. `POST /realtime/start`가 `mode`와 무관하게 항상 카테고리 10문항 중 3문항을 무작위로 뽑아 반환(순서도 함께 섞임). 결과 저장 시 `category`/`videotype` 필드 포함. 신규 엔드포인트 `GET /realtime/compare/{job_id}` — 같은 카테고리의 반대 모드(실시간 ↔ 실전연습) 중 가장 최근 완료된 결과와 점수 diff 비교.
- [Cap_Frontend/src/lib/api.js](Cap_Frontend/src/lib/api.js) — `startRealtimeInterview(category, mode)`, `compareRealtimeResults(jobId)`, `getRealtimeVideoUrl(jobId)` 추가.
- [Cap_Frontend/src/pages/RealtimeSetup.jsx](Cap_Frontend/src/pages/RealtimeSetup.jsx) — `location.state.mode`를 읽어 시작 요청/다음 페이지로 전달, 실전연습 모드 안내 문구 표시.
- [Cap_Frontend/src/pages/RealtimeInterview.jsx](Cap_Frontend/src/pages/RealtimeInterview.jsx) — 실전연습 모드일 때 웹캠 미리보기를 강제로 숨기고 토글 버튼도 숨김(녹화 자체는 정상 진행).
- [Cap_Frontend/src/pages/AnalysisLoading.jsx](Cap_Frontend/src/pages/AnalysisLoading.jsx) — `isRealtime` 플래그에 따라 `compareResults` 대신 `compareRealtimeResults` 호출.
- [Cap_Frontend/src/pages/ResultsDetail.jsx](Cap_Frontend/src/pages/ResultsDetail.jsx) — `videotype`이 있는 세션에는 "영상 보기" 섹션 추가(`<video>` 재생).

## 5. 로그인 프론트엔드 뼈대 (실제 인증 없음)

- [Cap_Frontend/src/context/AuthContext.jsx](Cap_Frontend/src/context/AuthContext.jsx) — `localStorage`에 아이디만 저장하는 방식. 비밀번호는 입력받아 즉시 버림(전송/저장 안 함). 향후 실제 백엔드 인증을 붙일 때의 목표 DB 스키마(`username | password | videotype | Datetime | filename | totalscore | category`)를 코드 주석으로만 남겨둠.
- [Cap_Frontend/src/pages/Login.jsx](Cap_Frontend/src/pages/Login.jsx), [Signup.jsx](Cap_Frontend/src/pages/Signup.jsx), [styles/Auth.module.css](Cap_Frontend/src/styles/Auth.module.css) 신규.
- [Cap_Frontend/src/main.jsx](Cap_Frontend/src/main.jsx) — `AuthProvider`로 앱 감싸기. [App.jsx](Cap_Frontend/src/App.jsx) — `/login`, `/signup` 라우트 추가.
- [Cap_Frontend/src/components/AppLogo.jsx](Cap_Frontend/src/components/AppLogo.jsx) — 전 페이지 우상단에 로그인 상태 뱃지(아이디 + 로그아웃 / 로그인 링크) 표시. `Home.jsx`는 `AppLogo`를 안 쓰므로 동일한 뱃지를 별도로 추가.
- 라우트 보호나 백엔드 연동은 하지 않음(의도적으로 범위 밖).

## 6. 홈 화면 버튼 레이아웃 조정 (후속 요청)

- [Cap_Frontend/src/pages/Home.jsx](Cap_Frontend/src/pages/Home.jsx), [Cap_Frontend/src/styles/Home.module.css](Cap_Frontend/src/styles/Home.module.css)
- 기존: "실전연습"을 "실시간 모의면접" 버튼 아래 작은 pill로 배치 → 사용자 요청으로 독립된 카드형 버튼으로 변경.
- 최종: 가운데 큰 버튼 두 개("실시간 모의면접", "모의면접 영상 분석")를 화면 정중앙 기준으로 정렬하고, "실전연습"(파란색)은 왼쪽 바깥, "지난기록 보기"(초록색)는 오른쪽 바깥에 `position: absolute`로 대칭 배치(`.buttonArea`는 `position: relative`, 두 버튼은 `right`/`left: calc(100% + 40px)`로 정렬 계산에서 제외).

## 7. 지난기록 보기 페이지 (후속 요청)

- [Cap_Frontend/src/pages/History.jsx](Cap_Frontend/src/pages/History.jsx), [styles/History.module.css](Cap_Frontend/src/styles/History.module.css) 신규.
- `GET /history`로 완료된 기록 목록을 카드 리스트로 표시(파일명/카테고리/모드 태그/날짜/평균 점수).
- 카드 클릭 시 `videotype` 유무에 따라 `compareRealtimeResults` 또는 `compareResults`를 호출해 비교 데이터를 가져온 뒤 `/results`로 이동.
- [App.jsx](Cap_Frontend/src/App.jsx)에 `/history` 라우트 추가, 홈 화면의 "지난기록 보기" 버튼에서 진입.

## 검증 상태

- 백엔드(Python)는 에이전트 실행 환경에 Python이 설치되어 있지 않아 직접 실행하지 못했고, `backend/main.py`는 전체를 다시 읽으며 라우트/구문/로직을 수기로 검토함.
- 프론트엔드는 사용자가 로컬에서 띄운 dev 서버(포트 5173, 실제 백엔드 연동됨)에 접속해 실제 확인:
  - 홈 화면 버튼 4개(실전연습/실시간 모의면접/모의면접 영상 분석/지난기록 보기) 배치 및 좌우 대칭 좌표 확인.
  - 로그인 → 홈 리다이렉트, 새로고침 후에도 로그인 상태 유지(localStorage) 확인.
  - 실전연습 모드 진입 시 안내 문구 노출 확인.
  - `/history` 페이지에서 실제 저장된 기록 27건 정상 로딩, 항목 클릭 시 `/realtime/compare/{job_id}` 호출 → `/results` 페이지에 실제 점수 표시까지 end-to-end 확인.
- 실제 카메라를 이용한 녹화 → 업로드 → 분석 전체 파이프라인, 그리고 실전연습 vs 일반 모드 점수 비교 화면은 사용자 환경에서 직접 진행하며 확인 필요.

## 참고 — 아직 하지 않은 것

- 실제 로그인 백엔드(비밀번호 검증, DB 저장, 세션/토큰) — 현재는 프론트엔드 로컬 상태만 존재.
- 사용자별 기록 구분 — 로그인이 실제로 붙기 전까지는 모든 기록이 전역으로 공유됨 (`/realtime/compare`도 "같은 카테고리 + 최근 완료" 기준으로만 매칭).
- 메모에 남아있던 DB 컬럼 설계(`username | password | videotype | Datetime | filename | totalscore | category`)는 실제 백엔드 인증을 구현할 때 참고할 목표 스키마로, 아직 미구현.
