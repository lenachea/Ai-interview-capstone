import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import AppLogo from '../components/AppLogo'
import styles from '../styles/History.module.css'
import { getHistory, compareResults, compareRealtimeResults } from '../lib/api'

const TYPE_LABELS = {
  realtime: '실시간 모의면접',
  practice: '실전연습',
}

function getGrade(score) {
  if (score == null) return { text: '대기 중', color: '#aaa' }
  if (score >= 90)   return { text: '매우 우수', color: '#50eba0' }
  if (score >= 75)   return { text: '우수',     color: '#5BB8F5' }
  if (score >= 60)   return { text: '보통',     color: '#f5b942' }
  return                    { text: '개선 필요', color: '#f07070' }
}

function formatDate(iso) {
  if (!iso) return ''
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return iso
  return d.toLocaleString('ko-KR', {
    year: 'numeric', month: '2-digit', day: '2-digit',
    hour: '2-digit', minute: '2-digit',
  })
}

function avgScore(scores) {
  if (!scores) return null
  const values = Object.values(scores).filter(v => typeof v === 'number')
  if (!values.length) return null
  return Math.round(values.reduce((a, b) => a + b, 0) / values.length)
}

export default function History() {
  const navigate = useNavigate()
  const [records, setRecords] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError]     = useState('')
  const [openingId, setOpeningId] = useState(null)

  useEffect(() => {
    getHistory()
      .then(setRecords)
      .catch(() => setError('기록을 불러오지 못했습니다. 백엔드 서버 상태를 확인해주세요.'))
      .finally(() => setLoading(false))
  }, [])

  async function openRecord(record) {
    if (openingId) return
    setOpeningId(record.job_id)
    try {
      const compareData = record.videotype
        ? await compareRealtimeResults(record.job_id)
        : await compareResults(record.job_id)
      navigate('/results', { state: { jobId: record.job_id, compareData } })
    } catch {
      setError('결과를 불러오지 못했습니다. 다시 시도해주세요.')
      setOpeningId(null)
    }
  }

  return (
    <div className={styles.container}>
      <AppLogo />
      <div className={styles.gradientMint} />
      <div className={styles.gradientBlue} />

      <div className={styles.content}>
        <h2 className={styles.title}>지난기록 보기</h2>

        {loading && <p className={styles.hint}>불러오는 중...</p>}
        {error && <p className={styles.error}>{error}</p>}

        {!loading && !error && records.length === 0 && (
          <p className={styles.hint}>아직 완료된 분석 기록이 없습니다.</p>
        )}

        <div className={styles.list}>
          {records.map((r) => {
            const avg = avgScore(r.scores)
            const grade = getGrade(avg)
            return (
              <button
                key={r.job_id}
                className={styles.card}
                onClick={() => openRecord(r)}
                disabled={openingId != null}
              >
                <div className={styles.cardMain}>
                  <span className={styles.cardFilename}>{r.filename || '모의면접'}</span>
                  <span className={styles.cardMeta}>
                    {r.category && <span className={styles.cardTag}>{r.category}</span>}
                    {r.videotype && (
                      <span className={styles.cardTag}>{TYPE_LABELS[r.videotype] || r.videotype}</span>
                    )}
                    <span className={styles.cardDate}>{formatDate(r.timestamp)}</span>
                  </span>
                </div>
                <div className={styles.cardScore}>
                  <span className={styles.scoreNum}>{avg != null ? `${avg}점` : '—'}</span>
                  <span className={styles.scoreGrade} style={{ color: grade.color }}>{grade.text}</span>
                </div>
              </button>
            )
          })}
        </div>

        <button className={styles.homeBtn} onClick={() => navigate('/')}>처음으로</button>
      </div>
    </div>
  )
}
