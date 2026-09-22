import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import AppLogo from '../components/AppLogo'
import styles from '../styles/Auth.module.css'
import { useAuth } from '../context/AuthContext'

export default function Signup() {
  const navigate = useNavigate()
  const { signup } = useAuth()
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [confirm, setConfirm] = useState('')
  const [error, setError] = useState('')

  function handleSubmit(e) {
    e.preventDefault()
    if (!username.trim() || !password) {
      setError('아이디와 비밀번호를 입력해주세요.')
      return
    }
    if (password !== confirm) {
      setError('비밀번호가 일치하지 않습니다.')
      return
    }
    // 실제 인증/DB 없음 — 아이디만 저장하고 홈으로 이동. 비밀번호는 저장/전송하지 않습니다.
    signup(username.trim())
    navigate('/')
  }

  return (
    <div className={styles.container}>
      <AppLogo />
      <div className={styles.gradientMint} />
      <div className={styles.gradientBlue} />

      <form className={styles.card} onSubmit={handleSubmit}>
        <h2 className={styles.title}>회원가입</h2>

        <div className={styles.field}>
          <label className={styles.label} htmlFor="username">아이디</label>
          <input
            id="username"
            className={styles.input}
            type="text"
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            autoComplete="username"
          />
        </div>

        <div className={styles.field}>
          <label className={styles.label} htmlFor="password">비밀번호</label>
          <input
            id="password"
            className={styles.input}
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            autoComplete="new-password"
          />
        </div>

        <div className={styles.field}>
          <label className={styles.label} htmlFor="confirm">비밀번호 확인</label>
          <input
            id="confirm"
            className={styles.input}
            type="password"
            value={confirm}
            onChange={(e) => setConfirm(e.target.value)}
            autoComplete="new-password"
          />
        </div>

        {error && <p className={styles.error}>{error}</p>}

        <button className={styles.submitBtn} type="submit">회원가입</button>

        <p className={styles.switchRow}>
          이미 계정이 있으신가요?
          <button type="button" className={styles.switchLink} onClick={() => navigate('/login')}>
            로그인
          </button>
        </p>
      </form>
    </div>
  )
}
