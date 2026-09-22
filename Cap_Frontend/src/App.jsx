import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { useAuth } from './context/AuthContext'
import Home from './pages/Home'
import RealtimeSetup from './pages/RealtimeSetup'
import RealtimeInterview from './pages/RealtimeInterview'
import VideoUpload from './pages/VideoUpload'
import AnalysisLoading from './pages/AnalysisLoading'
import ResultsOverview from './pages/ResultsOverview'
import ResultsDetail from './pages/ResultsDetail'
import Login from './pages/Login'
import History from './pages/History'
import AdminUsers from './pages/AdminUsers'

/** 로그인하지 않으면 /login 으로 리다이렉트 */
function PrivateRoute({ children }) {
  const { token } = useAuth()
  return token ? children : <Navigate to="/login" replace />
}

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        {/* 공개 라우트 — 로그인 없이 접근 가능 */}
        <Route path="/login" element={<Login />} />
        <Route path="/"      element={<Home />} />

        {/* 인증 필요 라우트 */}
        <Route path="/realtime"           element={<PrivateRoute><RealtimeSetup /></PrivateRoute>} />
        <Route path="/realtime/interview" element={<PrivateRoute><RealtimeInterview /></PrivateRoute>} />
        <Route path="/upload"             element={<PrivateRoute><VideoUpload /></PrivateRoute>} />
        <Route path="/loading"            element={<PrivateRoute><AnalysisLoading /></PrivateRoute>} />
        <Route path="/results"            element={<PrivateRoute><ResultsOverview /></PrivateRoute>} />
        <Route path="/results/detail"     element={<PrivateRoute><ResultsDetail /></PrivateRoute>} />
        <Route path="/history"            element={<PrivateRoute><History /></PrivateRoute>} />
        <Route path="/admin/users"        element={<PrivateRoute><AdminUsers /></PrivateRoute>} />

        {/* 이전 /signup 경로는 /login 으로 리다이렉트 */}
        <Route path="/signup" element={<Navigate to="/login" replace />} />
      </Routes>
    </BrowserRouter>
  )
}
