// vite.config.js의 프록시를 통해 /api → http://localhost:8000 으로 전달됩니다.
const BASE = '/api'

export async function uploadVideo(file) {
  const form = new FormData()
  form.append('file', file)
  const res = await fetch(`${BASE}/analyze`, { method: 'POST', body: form })
  if (!res.ok) throw new Error(`업로드 실패 (${res.status})`)
  return res.json()
}

export async function getResults(jobId) {
  const res = await fetch(`${BASE}/results/${jobId}`)
  if (!res.ok) throw new Error(`결과 조회 실패 (${res.status})`)
  return res.json()
}

export async function compareResults(jobId) {
  const res = await fetch(`${BASE}/compare/${jobId}`)
  if (!res.ok) throw new Error(`비교 조회 실패 (${res.status})`)
  return res.json()
}

export async function getHistory() {
  const res = await fetch(`${BASE}/history`)
  if (!res.ok) throw new Error(`기록 조회 실패 (${res.status})`)
  return res.json()
}
