// vite.config.js의 프록시를 통해 /api → http://localhost:8000 으로 전달됩니다.
const BASE = '/api'

/** 저장된 JWT 토큰을 Authorization 헤더로 반환합니다. */
function authHeader() {
  const token = localStorage.getItem('preview_token')
  return token ? { Authorization: `Bearer ${token}` } : {}
}

// ── 인증 ────────────────────────────────────────────────────────────────────

/**
 * 로그인 API 호출. 성공 시 { access_token, username, role } 반환.
 * 실패 시 서버 메시지로 Error를 throw합니다.
 */
export async function loginApi(username, password) {
  const res = await fetch(`${BASE}/auth/login`, {
    method:  'POST',
    headers: { 'Content-Type': 'application/json' },
    body:    JSON.stringify({ username, password }),
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(err.detail || '로그인에 실패했습니다.')
  }
  return res.json()
}

// ── 관리자 ───────────────────────────────────────────────────────────────────

export async function adminGetUsers() {
  const res = await fetch(`${BASE}/admin/users`, { headers: authHeader() })
  if (!res.ok) throw new Error('유저 목록을 가져오지 못했습니다.')
  return res.json()
}

export async function adminCreateUser(username, password, role = 'user') {
  const res = await fetch(`${BASE}/admin/users`, {
    method:  'POST',
    headers: { 'Content-Type': 'application/json', ...authHeader() },
    body:    JSON.stringify({ username, password, role }),
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(err.detail || '유저 생성에 실패했습니다.')
  }
  return res.json()
}

export async function adminDeleteUser(username) {
  const res = await fetch(`${BASE}/admin/users/${encodeURIComponent(username)}`, {
    method:  'DELETE',
    headers: authHeader(),
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(err.detail || '유저 삭제에 실패했습니다.')
  }
  return res.json()
}

// ── 분석 (기존 — Authorization 헤더 추가) ────────────────────────────────────

export async function uploadVideo(file) {
  const form = new FormData()
  form.append('file', file)
  const res = await fetch(`${BASE}/analyze`, { method: 'POST', headers: authHeader(), body: form })
  if (!res.ok) throw new Error(`업로드 실패 (${res.status})`)
  return res.json()
}

export async function getResults(jobId) {
  const res = await fetch(`${BASE}/results/${jobId}`, { headers: authHeader() })
  if (!res.ok) throw new Error(`결과 조회 실패 (${res.status})`)
  return res.json()
}

export async function compareResults(jobId) {
  const res = await fetch(`${BASE}/compare/${jobId}`, { headers: authHeader() })
  if (!res.ok) throw new Error(`비교 조회 실패 (${res.status})`)
  return res.json()
}

export async function getHistory() {
  const res = await fetch(`${BASE}/history`, { headers: authHeader() })
  if (!res.ok) throw new Error(`기록 조회 실패 (${res.status})`)
  return res.json()
}

// ── 실시간 모의면접 ──────────────────────────────────────────────────────────

export async function getRealtimeQuestions() {
  const res = await fetch(`${BASE}/realtime/questions`, { headers: authHeader() })
  if (!res.ok) throw new Error(`질문 목록 조회 실패 (${res.status})`)
  return res.json()
}

export async function startRealtimeInterview(category, mode = 'realtime') {
  const res = await fetch(`${BASE}/realtime/start`, {
    method:  'POST',
    headers: { 'Content-Type': 'application/json', ...authHeader() },
    body:    JSON.stringify({ category, mode }),
  })
  if (!res.ok) throw new Error(`면접 시작 실패 (${res.status})`)
  return res.json()
}

export async function finishRealtimeInterview(jobId, videoBlob, timestamps) {
  const form = new FormData()
  form.append('file', videoBlob, 'video.webm')
  form.append('timestamps', JSON.stringify(timestamps))
  const res = await fetch(`${BASE}/realtime/${jobId}/finish`, {
    method:  'POST',
    headers: authHeader(),
    body:    form,
  })
  if (!res.ok) throw new Error(`면접 종료 처리 실패 (${res.status})`)
  return res.json()
}

export function getRealtimeVideoUrl(jobId) {
  return `${BASE}/realtime/${jobId}/video`
}

export async function compareRealtimeResults(jobId) {
  const res = await fetch(`${BASE}/realtime/compare/${jobId}`, { headers: authHeader() })
  if (!res.ok) throw new Error(`비교 조회 실패 (${res.status})`)
  return res.json()
}
