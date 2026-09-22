import { useNavigate } from 'react-router-dom'
import styles from '../styles/Home.module.css'
import authStyles from '../styles/AppLogo.module.css'
import { useAuth } from '../context/AuthContext'

export default function Home() {
  const navigate = useNavigate()
  const auth = useAuth()

  return (
    <div className={styles.container}>
      {/* 배경 줄무늬 장식 */}
      <div className={styles.gradientMint} />
      <div className={styles.gradientBlue} />

      {/* 로그인 상태 뱃지 */}
      <div className={authStyles.authBadge}>
        {auth?.user ? (
          <>
            <span className={authStyles.authUser}>{auth.user.username}님</span>
            <button className={authStyles.authLink} onClick={() => auth.logout()}>로그아웃</button>
          </>
        ) : (
          <button className={authStyles.authLink} onClick={() => navigate('/login')}>로그인</button>
        )}
      </div>

      <div className={styles.content}>
        {/* 로고 영역 */}
        <div className={styles.logoArea}>
          <img src="/logo2.png" alt="PreView" className={styles.logoImg} />
          <p className={styles.subtitle}>긴장되시나요? 도와드리겠습니다!</p>
        </div>

        {/* 버튼 영역 */}
        <div className={styles.buttonArea}>
          {/* 실전연습 버튼 (독립 카드) */}
          <button
            className={styles.practiceBtn}
            onClick={() => navigate('/realtime', { state: { mode: 'practice' } })}
          >
            <span className={styles.btnLabel}>실전 연습</span>
          </button>

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

          {/* 지난기록 보기 버튼 (독립 카드, 실전연습과 대칭) */}
          <button
            className={styles.historyBtn}
            onClick={() => navigate('/history')}
          >
            <span className={styles.btnLabel}>지난 기록 보기</span>
          </button>
        </div>
      </div>
    </div>
  )
}
