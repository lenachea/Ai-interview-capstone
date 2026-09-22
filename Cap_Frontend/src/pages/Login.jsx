import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import AppLogo from '../components/AppLogo'
import styles from '../styles/Auth.module.css'
import { useAuth } from '../context/AuthContext'

export default function Login() {
  const navigate  = useNavigate()
  const { login } = useAuth()
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error,    setError]    = useState('')
  const [loading,  setLoading]  = useState(false)
  const [showPw,   setShowPw]   = useState(false)

  async function handleSubmit(e) {
    e.preventDefault()
    if (!username.trim() || !password) {
      setError('아이디와 비밀번호를 입력해주세요.')
      return
    }
    setError('')
    setLoading(true)
    try {
      await login(username.trim(), password)
      navigate('/')
    } catch (err) {
      setError(err.message || '로그인에 실패했습니다.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className={styles.container}>
      <AppLogo />
      <div className={styles.gradientMint} />
      <div className={styles.gradientBlue} />

      <form className={styles.card} onSubmit={handleSubmit}>
        <h2 className={styles.title}>로그인</h2>

        <div className={styles.field}>
          <label className={styles.label} htmlFor="username">아이디</label>
          <input
            id="username"
            className={styles.input}
            type="text"
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            autoComplete="username"
            disabled={loading}
          />
        </div>

        <div className={styles.field}>
          <label className={styles.label} htmlFor="password">비밀번호</label>
          <div className={styles.passwordWrap}>
            <input
              id="password"
              className={styles.input}
              type={showPw ? 'text' : 'password'}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              autoComplete="current-password"
              disabled={loading}
            />
            <button
              type="button"
              className={styles.eyeBtn}
              onClick={() => setShowPw(v => !v)}
              tabIndex={-1}
              aria-label={showPw ? '비밀번호 숨기기' : '비밀번호 보기'}
            >
              {showPw ? 'Ⓧ' : 'Ⓞ'}
            </button>
          </div>
        </div>

        {error && <p className={styles.error}>{error}</p>}

        <button className={styles.submitBtn} type="submit" disabled={loading}>
          {loading ? '로그인 중...' : '로그인'}
        </button>
      </form>
    </div>
  )
}
