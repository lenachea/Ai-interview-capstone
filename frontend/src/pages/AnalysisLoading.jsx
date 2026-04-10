import { useEffect } from 'react'
import { useNavigate, useLocation } from 'react-router-dom'
import AppLogo from '../components/AppLogo'
import styles from '../styles/AnalysisLoading.module.css'

export default function AnalysisLoading() {
  const navigate = useNavigate()
  const location = useLocation()
  const fileName = location.state?.fileName || '영상'

  // 목업: 3초 후 결과 페이지로 이동
  useEffect(() => {
    const timer = setTimeout(() => {
      navigate('/results')
    }, 3000)
    return () => clearTimeout(timer)
  }, [navigate])

  return (
    <div className={styles.container}>
      <AppLogo />
      <div className={styles.stripesMint} />
      <div className={styles.stripesBlue} />
      <div className={styles.card}>
        {/* 영상 파일 아이콘 */}
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

        {/* 그라데이션 로딩 바 */}
        <div className={styles.progressTrack}>
          <div className={styles.progressBar} />
        </div>

        <p className={styles.hint}>잠시만 기다려주세요</p>
      </div>
    </div>
  )
}
