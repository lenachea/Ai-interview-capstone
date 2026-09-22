import { useState, useEffect, useRef, useCallback } from 'react'
import { useNavigate, useLocation } from 'react-router-dom'
import AppLogo from '../components/AppLogo'
import styles from '../styles/RealtimeInterview.module.css'
import { finishRealtimeInterview } from '../lib/api'

const MIME_CANDIDATES = [
  'video/webm;codecs=vp9,opus',
  'video/webm;codecs=vp8,opus',
  'video/webm',
]

function pickMimeType() {
  if (!window.MediaRecorder) return ''
  return MIME_CANDIDATES.find(type => MediaRecorder.isTypeSupported(type)) || ''
}

export default function RealtimeInterview() {
  const navigate = useNavigate()
  const location = useLocation()
  const jobId     = location.state?.jobId
  const questions = location.state?.questions
  const category  = location.state?.category || '실시간 모의면접'
  const mode      = location.state?.mode || 'realtime'
  const isPractice = mode === 'practice'

  const videoRef   = useRef(null)
  const streamRef  = useRef(null)
  const recorderRef = useRef(null)
  const chunksRef  = useRef([])
  const recordingStartRef = useRef(0)
  const timestampsRef     = useRef([])
  const boundaryRef       = useRef(0)

  const [currentIndex,  setCurrentIndex]  = useState(0)
  const [previewHidden, setPreviewHidden] = useState(isPractice)
  const [recording,     setRecording]     = useState(false)
  const [uploading,     setUploading]     = useState(false)
  const [deviceReady,   setDeviceReady]   = useState(false)
  const [error,         setError]         = useState('')

  const validEntry = Boolean(jobId && questions && questions.length > 0)
  const isLast = validEntry && currentIndex === questions.length - 1

  // 잘못된 진입(직접 URL 접근 등) 시 설정 화면으로
  useEffect(() => {
    if (!validEntry) navigate('/realtime')
  }, [validEntry, navigate])

  // 웹캠/마이크 스트림 확보
  useEffect(() => {
    let cancelled = false
    navigator.mediaDevices.getUserMedia({ video: true, audio: true })
      .then(stream => {
        if (cancelled) {
          stream.getTracks().forEach(t => t.stop())
          return
        }
        streamRef.current = stream
        if (videoRef.current) videoRef.current.srcObject = stream
        setDeviceReady(true)
      })
      .catch(() => setError('웹캠/마이크에 접근할 수 없습니다. 권한을 확인해주세요.'))

    return () => {
      cancelled = true
      window.speechSynthesis?.cancel()
      try {
        if (recorderRef.current?.state === 'recording') recorderRef.current.stop()
      } catch { /* noop */ }
      streamRef.current?.getTracks().forEach(t => t.stop())
    }
  }, [])

  const speak = useCallback((text) => {
    if (!window.speechSynthesis) return
    window.speechSynthesis.cancel()
    const utter = new SpeechSynthesisUtterance(text)
    utter.lang = 'ko-KR'
    window.speechSynthesis.speak(utter)
  }, [])

  const startRecording = useCallback(() => {
    if (!streamRef.current) return
    const mimeType = pickMimeType()
    const recorder = mimeType
      ? new MediaRecorder(streamRef.current, { mimeType })
      : new MediaRecorder(streamRef.current)
    chunksRef.current = []
    recorder.ondataavailable = (e) => {
      if (e.data && e.data.size > 0) chunksRef.current.push(e.data)
    }
    recorder.start()
    recorderRef.current = recorder
    recordingStartRef.current = performance.now()
    setRecording(true)
  }, [])

  // 면접 시작 시 단 한 번만 녹화를 시작 — 이후 질문이 바뀌어도 녹화는 끊기지 않고 계속됩니다.
  useEffect(() => {
    if (!deviceReady || !validEntry) return
    startRecording()
  }, [deviceReady, validEntry, startRecording])

  // 질문이 바뀔 때마다 TTS만 재생 (녹화와는 무관)
  useEffect(() => {
    if (!deviceReady || !validEntry) return
    speak(questions[currentIndex])
  }, [deviceReady, currentIndex, validEntry, questions, speak])

  async function handleNext() {
    if (uploading || !recording || !recorderRef.current) return

    const elapsed = (performance.now() - recordingStartRef.current) / 1000
    timestampsRef.current.push({
      index: currentIndex,
      question: questions[currentIndex],
      start: boundaryRef.current,
      end: elapsed,
    })
    boundaryRef.current = elapsed

    if (!isLast) {
      setCurrentIndex(i => i + 1)
      return
    }

    setUploading(true)
    setError('')

    const recorder = recorderRef.current
    const blob = await new Promise((resolve) => {
      recorder.onstop = () => {
        resolve(new Blob(chunksRef.current, { type: recorder.mimeType || 'video/webm' }))
      }
      recorder.stop()
    })
    setRecording(false)

    try {
      await finishRealtimeInterview(jobId, blob, timestampsRef.current)
      navigate('/loading', { state: { jobId, fileName: `${category} 모의면접`, isRealtime: true } })
    } catch {
      setError('업로드에 실패했습니다. 네트워크 상태를 확인 후 다시 시도해주세요.')
      setUploading(false)
    }
  }

  if (!validEntry) return null

  return (
    <div className={styles.container}>
      <AppLogo />
      <div className={styles.gradientMint} />
      <div className={styles.gradientBlue} />

      <div className={styles.content}>
        <div className={styles.questionPill}>
          <span className={styles.categoryTag}>{category}</span>
          <span className={styles.questionMeta}>질문 {currentIndex + 1} / {questions.length}</span>
          <p className={styles.questionText}>{questions[currentIndex]}</p>
        </div>

        <div className={styles.videoWrap}>
          <video
            ref={videoRef}
            autoPlay
            muted
            playsInline
            className={`${styles.video} ${previewHidden ? styles.videoHidden : ''}`}
          />
          {previewHidden && (
            <div className={styles.videoHiddenOverlay}>
              <svg className={styles.silhouette} viewBox="0 0 120 120" fill="none" xmlns="http://www.w3.org/2000/svg">
                <circle cx="60" cy="38" r="22" stroke="currentColor" strokeWidth="2.5" />
                <path d="M22 100 C22 68 40 56 60 56 C80 56 98 68 98 100" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" />
              </svg>
              <span>웹캠 화면이 가려져 있습니다</span>
            </div>
          )}
          {recording && (
            <span className={styles.recIndicator}>
              <span className={styles.recDot} /> 녹화 중
            </span>
          )}
        </div>

        {error && <p className={styles.error}>{error}</p>}

        <div className={styles.actions}>
          {!isPractice && (
            <button className={styles.toggleBtn} onClick={() => setPreviewHidden(h => !h)}>
              {previewHidden ? '웹캠 화면 보기' : '웹캠 화면 가리기'}
            </button>
          )}
          <button className={styles.nextBtn} disabled={!recording || uploading} onClick={handleNext}>
            {uploading ? '업로드 중...' : (isLast ? '면접 종료' : '다음 질문')}
          </button>
        </div>
      </div>
    </div>
  )
}
