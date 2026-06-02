import { useEffect, useRef } from 'react'
import { useNavigate, useLocation } from 'react-router-dom'
import AppLogo from '../components/AppLogo'
import styles from '../styles/AnalysisLoading.module.css'
import { getResults, compareResults } from '../lib/api'

const POLL_INTERVAL_MS = 3000

export default function AnalysisLoading() {
  const navigate = useNavigate()
  const location = useLocation()
  const fileName = location.state?.fileName || '영상'
  const jobId    = location.state?.jobId   || null
  const timerRef = useRef(null)

  useEffect(() => {
    if (!jobId) {
      // 백엔드 없이 접근한 경우 (직접 URL 입력 등) - 5초 대기 후 목업 결과로 이동
      timerRef.current = setTimeout(() => navigate('/results'), 5000)
      return () => clearTimeout(timerRef.current)
    }

    timerRef.current = setInterval(async () => {
      try {
        const result = await getResults(jobId)

        if (result.status === 'completed') {
          clearInterval(timerRef.current)
          // 비교 데이터 미리 fetch
          try {
            const compareData = await compareResults(jobId)
            navigate('/results', { state: { jobId, compareData } })
          } catch {
            navigate('/results', { state: { jobId, compareData: { current: result, previous: null, diff: {} } } })
          }
        } else if (result.status === 'failed') {
          clearInterval(timerRef.current)
          navigate('/results', { state: { jobId, error: result.error || '분석에 실패했습니다.' } })
        }
        // status === 'processing'이면 계속 대기
      } catch (err) {
        console.error('[Polling]', err)
      }
    }, POLL_INTERVAL_MS)

    return () => clearInterval(timerRef.current)
  }, [jobId, navigate])

  return (
    <div className={styles.container}>
      <AppLogo />
      <div className={styles.gradientMint} />
      <div className={styles.gradientBlue} />
      <div className={styles.card}>
        <div className={styles.iconWrap}>
          <svg viewBox="0 0 80 80" fill="none" xmlns="http://www.w3.org/2000/svg">
            <circle cx="40" cy="40" r="38" fill="url(#grad)" opacity="0.15"/>
            <rect x="18" y="20" width="44" height="40" rx="6" fill="url(#grad)" opacity="0.3"/>
            <polygon points="32,28 56,40 32,52" fill="url(#grad)"/>
            <defs>
              <linearGradient id="grad" x1="0" y1="0" x2="80" y2="80" gradientUnits="userSpaceOnUse">
                <stop offset="0%" stopColor="#50eba0"/>
                <stop offset="100%" stopColor="#5BB8F5"/>
              </linearGradient>
            </defs>
          </svg>
        </div>

        <h2 className={styles.title}>업로드하신 영상을 분석 중입니다...</h2>
        <p className={styles.fileName}>📄 {fileName}</p>
        <p className={styles.desc}>표정, 자세, 말하기 항목을 분석하고 있습니다</p>

        <div className={styles.progressTrack}>
          <div className={styles.progressBar} />
        </div>

        <p className={styles.hint}>
          {jobId ? '분석이 완료되면 자동으로 이동합니다' : '잠시만 기다려주세요'}
        </p>
      </div>
    </div>
  )
}
