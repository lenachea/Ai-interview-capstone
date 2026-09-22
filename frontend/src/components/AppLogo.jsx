import { useNavigate } from 'react-router-dom'
import styles from '../styles/AppLogo.module.css'

/**
 * 다른 페이지 좌측 상단에 고정되는 작은 로고 컴포넌트.
 * 클릭하면 홈(/)으로 이동합니다.
 */
export default function AppLogo() {
  const navigate = useNavigate()

  return (
    <button
      className={styles.wrap}
      onClick={() => navigate('/')}
      aria-label="홈으로 이동"
    >
      <img src="/logo.png" alt="PreView" className={styles.logo} />
    </button>
  )
}
