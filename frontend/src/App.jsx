import { BrowserRouter, Routes, Route } from 'react-router-dom'
import Home from './pages/Home'
import RealtimeSetup from './pages/RealtimeSetup'
import VideoUpload from './pages/VideoUpload'
import AnalysisLoading from './pages/AnalysisLoading'
import ResultsOverview from './pages/ResultsOverview'
import ResultsDetail from './pages/ResultsDetail'

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<Home />} />
        <Route path="/realtime" element={<RealtimeSetup />} />
        <Route path="/upload" element={<VideoUpload />} />
        <Route path="/loading" element={<AnalysisLoading />} />
        <Route path="/results" element={<ResultsOverview />} />
        <Route path="/results/detail" element={<ResultsDetail />} />
      </Routes>
    </BrowserRouter>
  )
}
