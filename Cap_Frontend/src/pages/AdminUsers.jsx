import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import AppLogo from '../components/AppLogo'
import { useAuth } from '../context/AuthContext'
import { adminGetUsers, adminCreateUser, adminDeleteUser } from '../lib/api'
import styles from '../styles/AdminUsers.module.css'

export default function AdminUsers() {
  const navigate      = useNavigate()
  const { user }      = useAuth()
  const [users,    setUsers]    = useState([])
  const [loading,  setLoading]  = useState(true)
  const [error,    setError]    = useState('')
  const [showForm, setShowForm] = useState(false)

  // 새 유저 폼 상태
  const [newUsername, setNewUsername] = useState('')
  const [newPassword, setNewPassword] = useState('')
  const [newRole,     setNewRole]     = useState('user')
  const [formError,   setFormError]   = useState('')
  const [formLoading, setFormLoading] = useState(false)

  // admin이 아니면 홈으로
  useEffect(() => {
    if (user && user.role !== 'admin') navigate('/')
    if (!user) navigate('/login')
  }, [user, navigate])

  function fetchUsers() {
    setLoading(true)
    adminGetUsers()
      .then(setUsers)
      .catch(() => setError('유저 목록을 불러오지 못했습니다.'))
      .finally(() => setLoading(false))
  }

  useEffect(() => { fetchUsers() }, [])

  async function handleCreate(e) {
    e.preventDefault()
    if (!newUsername.trim() || !newPassword) {
      setFormError('아이디와 비밀번호를 입력해주세요.')
      return
    }
    setFormError('')
    setFormLoading(true)
    try {
      await adminCreateUser(newUsername.trim(), newPassword, newRole)
      setNewUsername('')
      setNewPassword('')
      setNewRole('user')
      setShowForm(false)
      fetchUsers()
    } catch (err) {
      setFormError(err.message)
    } finally {
      setFormLoading(false)
    }
  }

  async function handleDelete(username) {
    if (!window.confirm(`'${username}' 계정을 삭제하시겠습니까?`)) return
    try {
      await adminDeleteUser(username)
      fetchUsers()
    } catch (err) {
      setError(err.message)
    }
  }

  return (
    <div className={styles.container}>
      <AppLogo />
      <div className={styles.gradientMint} />
      <div className={styles.gradientBlue} />

      <div className={styles.content}>
        <div className={styles.header}>
          <h2 className={styles.title}>유저 관리</h2>
          <button className={styles.addBtn} onClick={() => setShowForm(v => !v)}>
            {showForm ? '취소' : '+ 유저 추가'}
          </button>
        </div>

        {/* 유저 추가 폼 */}
        {showForm && (
          <form className={styles.form} onSubmit={handleCreate}>
            <div className={styles.formRow}>
              <input
                className={styles.formInput}
                placeholder="아이디"
                value={newUsername}
                onChange={e => setNewUsername(e.target.value)}
                disabled={formLoading}
              />
              <input
                className={styles.formInput}
                placeholder="비밀번호"
                type="password"
                value={newPassword}
                onChange={e => setNewPassword(e.target.value)}
                disabled={formLoading}
              />
              <select
                className={styles.formSelect}
                value={newRole}
                onChange={e => setNewRole(e.target.value)}
                disabled={formLoading}
              >
                <option value="user">user</option>
                <option value="admin">admin</option>
              </select>
              <button className={styles.createBtn} type="submit" disabled={formLoading}>
                {formLoading ? '생성 중...' : '생성'}
              </button>
            </div>
            {formError && <p className={styles.formError}>{formError}</p>}
          </form>
        )}

        {/* 에러 */}
        {error && <p className={styles.error}>{error}</p>}

        {/* 유저 테이블 */}
        {loading ? (
          <p className={styles.hint}>불러오는 중...</p>
        ) : (
          <table className={styles.table}>
            <thead>
              <tr>
                <th>아이디</th>
                <th>권한</th>
                <th>생성일</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {users.map(u => (
                <tr key={u.id}>
                  <td>{u.username}</td>
                  <td>
                    <span className={u.role === 'admin' ? styles.badgeAdmin : styles.badgeUser}>
                      {u.role}
                    </span>
                  </td>
                  <td className={styles.dateCell}>{u.created_at?.slice(0, 10)}</td>
                  <td>
                    {u.role !== 'admin' && (
                      <button
                        className={styles.deleteBtn}
                        onClick={() => handleDelete(u.username)}
                      >
                        삭제
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}

        <button className={styles.backBtn} onClick={() => navigate('/')}>홈으로</button>
      </div>
    </div>
  )
}
