import { useNavigate } from 'react-router-dom'
import styles from '../styles/Home.module.css'

export default function Home() {
  const navigate = useNavigate()

  return (
    <div className={styles.container}>
      {/* 배경 줄무늬 장식 */}
      <div className={styles.stripesMint} />
      <div className={styles.stripesBlue} />

      <div className={styles.content}>
        {/* 로고 영역 */}
        <div className={styles.logoArea}>
          <img src="/logo.png" alt="PreView" className={styles.logoImg} />
          <p className={styles.subtitle}>긴장하셨나요? 도와드리겠습니다!</p>
        </div>

        {/* 버튼 영역 */}
        <div className={styles.buttonArea}>
          {/* 실시간 모의면접 버튼 */}
          <button
            className={`${styles.navBtn} ${styles.btnBlue}`}
            onClick={() => navigate('/realtime')}
          >
            <div className={styles.btnIcon}>
              {/* 카메라 아이콘 */}
              <svg viewBox="0 0 48 48" fill="none" xmlns="http://www.w3.org/2000/svg">
                <rect x="4" y="12" width="32" height="24" rx="4" fill="white" opacity="0.9"/>
                <circle cx="20" cy="24" r="7" fill="white" opacity="0.7"/>
                <circle cx="20" cy="24" r="4" fill="white"/>
                <rect x="14" y="8" width="8" height="4" rx="2" fill="white" opacity="0.9"/>
                <polygon points="36,18 44,14 44,34 36,30" fill="white" opacity="0.8"/>
              </svg>
            </div>
            <span className={styles.btnLabel}>실시간 모의면접</span>
          </button>

          {/* 모의면접 영상 분석 버튼 */}
          <button
            className={`${styles.navBtn} ${styles.btnGreen}`}
            onClick={() => navigate('/upload')}
          >
            <div className={styles.btnIcon}>
              {/* 필름 아이콘 */}
              <svg viewBox="0 0 48 48" fill="none" xmlns="http://www.w3.org/2000/svg">
                <rect x="6" y="10" width="36" height="28" rx="3" fill="white" opacity="0.9"/>
                <rect x="6" y="10" width="7" height="28" rx="2" fill="white" opacity="0.6"/>
                <rect x="35" y="10" width="7" height="28" rx="2" fill="white" opacity="0.6"/>
                <rect x="10" y="14" width="3" height="4" rx="1" fill="#50eba0"/>
                <rect x="10" y="21" width="3" height="4" rx="1" fill="#50eba0"/>
                <rect x="10" y="28" width="3" height="4" rx="1" fill="#50eba0"/>
                <rect x="35" y="14" width="3" height="4" rx="1" fill="#50eba0"/>
                <rect x="35" y="21" width="3" height="4" rx="1" fill="#50eba0"/>
                <rect x="35" y="28" width="3" height="4" rx="1" fill="#50eba0"/>
                <rect x="16" y="14" width="16" height="20" rx="2" fill="white" opacity="0.5"/>
              </svg>
            </div>
            <span className={styles.btnLabel}>모의면접 영상 분석</span>
          </button>
        </div>
      </div>
    </div>
  )
}
