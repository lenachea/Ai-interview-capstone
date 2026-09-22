import { useNavigate } from 'react-router-dom'
import styles from '../styles/AppLogo.module.css'
import { useAuth } from '../context/AuthContext'

/**
 * 다른 페이지 좌측 상단에 고정되는 작은 로고 컴포넌트.
 * 클릭하면 홈(/)으로 이동합니다. 우측 상단에는 로그인 상태 뱃지를 함께 표시합니다.
 */
export default function AppLogo() {
  const navigate = useNavigate()
  const auth = useAuth()

  return (
    <>
      <button
        className={styles.wrap}
        onClick={() => navigate('/')}
        aria-label="홈으로 이동"
      >
        <img src="/logo.png" alt="PreView" className={styles.logo} />
      </button>

      <div className={styles.authBadge}>
        {auth?.user ? (
          <>
            <span className={styles.authUser}>{auth.user.username}님</span>
            <button className={styles.authLink} onClick={() => auth.logout()}>로그아웃</button>
          </>
        ) : (
          <button className={styles.authLink} onClick={() => navigate('/login')}>로그인</button>
        )}
      </div>
    </>
  )
}
