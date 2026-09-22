import { createContext, useContext, useState } from 'react'
import { loginApi } from '../lib/api'

const STORAGE_KEY = 'preview_token'
const AuthContext = createContext(null)

export function AuthProvider({ children }) {
  const [token, setToken]   = useState(() => localStorage.getItem(STORAGE_KEY))
  const [user,  setUser]    = useState(() => {
    try {
      const t = localStorage.getItem(STORAGE_KEY)
      if (!t) return null
      // JWT payload 디코딩 (검증 없이 표시용으로만 사용)
      const payload = JSON.parse(atob(t.split('.')[1]))
      return { username: payload.sub, role: payload.role }
    } catch { return null }
  })

  /**
   * 로그인: 백엔드에 username/password를 보내고 JWT를 받아 저장합니다.
   * 성공 시 true, 실패 시 에러 메시지(string)를 throw합니다.
   */
  async function login(username, password) {
    const data = await loginApi(username, password)   // throws on error
    localStorage.setItem(STORAGE_KEY, data.access_token)
    setToken(data.access_token)
    setUser({ username: data.username, role: data.role })
  }

  function logout() {
    localStorage.removeItem(STORAGE_KEY)
    setToken(null)
    setUser(null)
  }

  return (
    <AuthContext.Provider value={{ token, user, login, logout }}>
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth() {
  return useContext(AuthContext)
}
