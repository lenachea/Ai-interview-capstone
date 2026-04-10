import { useState, useEffect, useRef, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import AppLogo from '../components/AppLogo'
import styles from '../styles/RealtimeSetup.module.css'

const STATUS_INFO = {
  checking: { label: '확인 중...', color: '#aaa' },
  granted:  { label: '허용됨',    color: '#50eba0' },
  denied:   { label: '거부됨',    color: '#f07070' },
}

// ── 면접 준비 안내 문구 ──────────────────────────────────────────────
// 이 배열을 수정하면 우측 안내 패널의 내용이 바뀝니다.
// GUIDE.md의 "면접 준비 안내 문구 수정" 섹션을 참고하세요.
const GUIDANCE_ITEMS = [
  {
    icon: '📷',
    title: '카메라 위치',
    tips: [
      '카메라를 눈높이에 맞춰 정면으로 향하게 해주세요.',
      '얼굴 전체가 화면 중앙에 잘 보이도록 거리를 조절하세요.',
      '배경은 단색의 밝은 벽이나 커튼이 적합합니다.',
    ],
  },
  {
    icon: '💡',
    title: '조명',
    tips: [
      '밝고 자연스러운 빛이 얼굴 정면을 향하도록 해주세요.',
      '역광(창문을 등지고 앉기)은 피해 주세요.',
    ],
  },
  {
    icon: '🎙️',
    title: '마이크',
    tips: [
      '주변 소음이 적은 조용한 환경에서 진행해 주세요.',
      '마이크와 적절한 거리(30~50cm)를 유지하세요.',
    ],
  },
  {
    icon: '👔',
    title: '복장',
    tips: [
      '단색 또는 무늬가 단순한 상의를 착용하면 자세 분석이 더 정확합니다.',
      '실제 면접처럼 단정한 복장을 권장합니다.',
    ],
  },
]
// ─────────────────────────────────────────────────────────────────────

export default function RealtimeSetup() {
  const navigate = useNavigate()
  const videoRef     = useRef(null)
  const canvasRef    = useRef(null)
  const streamsRef   = useRef([])
  const analyserRef  = useRef(null)
  const audioCtxRef  = useRef(null)
  const animFrameRef = useRef(null)

  const [cameraStatus, setCameraStatus] = useState('checking')
  const [micStatus,    setMicStatus]    = useState('checking')

  // ── VU 미터 (좌→우로 커졌다 작아지는 수평 레벨 바) ─────────────
  const startVolumeViz = useCallback((stream) => {
    try {
      const audioCtx = new (window.AudioContext || window.webkitAudioContext)()
      audioCtxRef.current = audioCtx
      const source   = audioCtx.createMediaStreamSource(stream)
      const analyser = audioCtx.createAnalyser()
      analyser.fftSize = 256
      analyser.smoothingTimeConstant = 0.6   // 부드러운 반응
      source.connect(analyser)
      analyserRef.current = analyser

      function tick() {
        const canvas = canvasRef.current
        const a      = analyserRef.current
        if (!canvas || !a) return

        const ctx  = canvas.getContext('2d')
        const data = new Uint8Array(a.frequencyBinCount)
        a.getByteFrequencyData(data)

        // RMS 방식으로 볼륨 레벨 계산 → 민감도 조절
        const rms   = Math.sqrt(data.reduce((s, v) => s + v * v, 0) / data.length)
        const level = Math.min(1, rms / 80)   // 0~1 (80 = 기준값, 낮을수록 민감)

        const w  = canvas.width
        const h  = canvas.height
        const bh = 12          // 바 높이
        const r  = bh / 2      // 둥근 모서리
        const y  = (h - bh) / 2

        ctx.clearRect(0, 0, w, h)

        // 배경 트랙
        ctx.fillStyle = '#e0e0e0'
        ctx.beginPath()
        ctx.roundRect(0, y, w, bh, r)
        ctx.fill()

        // 볼륨 채우기 (초록 → 파랑 그라데이션)
        if (level > 0.01) {
          const grad = ctx.createLinearGradient(0, 0, w, 0)
          grad.addColorStop(0, '#50eba0')
          grad.addColorStop(1, '#5BB8F5')
          ctx.fillStyle = grad
          ctx.beginPath()
          ctx.roundRect(0, y, w * level, bh, r)
          ctx.fill()
        }

        animFrameRef.current = requestAnimationFrame(tick)
      }
      tick()
    } catch (e) {
      console.warn('Audio visualization error:', e)
    }
  }, [])

  useEffect(() => {
    async function checkDevices() {
      try {
        const stream = await navigator.mediaDevices.getUserMedia({ video: true, audio: true })
        streamsRef.current.push(stream)
        setCameraStatus('granted')
        setMicStatus('granted')
        if (videoRef.current) videoRef.current.srcObject = stream
        startVolumeViz(stream)
      } catch (err) {
        const isDenied = err.name === 'NotAllowedError' || err.name === 'PermissionDeniedError'
        if (isDenied) {
          setCameraStatus('denied')
          setMicStatus('denied')
        } else {
          try {
            const vs = await navigator.mediaDevices.getUserMedia({ video: true })
            streamsRef.current.push(vs)
            setCameraStatus('granted')
            if (videoRef.current) videoRef.current.srcObject = vs
          } catch { setCameraStatus('denied') }
          try {
            const as = await navigator.mediaDevices.getUserMedia({ audio: true })
            streamsRef.current.push(as)
            setMicStatus('granted')
            startVolumeViz(as)
          } catch { setMicStatus('denied') }
        }
      }
    }

    checkDevices()

    return () => {
      cancelAnimationFrame(animFrameRef.current)
      audioCtxRef.current?.close()
      streamsRef.current.forEach(s => s.getTracks().forEach(t => t.stop()))
      streamsRef.current = []
      if (videoRef.current) videoRef.current.srcObject = null
    }
  }, [startVolumeViz])

  const allGranted = cameraStatus === 'granted' && micStatus === 'granted'
  const camInfo    = STATUS_INFO[cameraStatus]
  const micInfo    = STATUS_INFO[micStatus]

  return (
    <div className={styles.container}>
      <AppLogo />
      <div className={styles.stripesMint} />
      <div className={styles.stripesBlue} />

      <div className={styles.content}>
        <div className={styles.pageHeader}>
          <h2 className={styles.title}>장치 상태 확인</h2>
          <p className={styles.desc}>면접 시작 전 웹캠과 마이크 권한을 허용해주세요.</p>
        </div>

        {/* ── 좌우 2열 레이아웃 ── */}
        <div className={styles.mainGrid}>

          {/* 좌측: 장치 카드 */}
          <div className={styles.deviceSection}>

            {/* 웹캠 섹션 */}
            <div className={styles.cameraCard}>
              <div className={styles.cardHeader}>
                <div className={styles.cardLabelRow}>
                  <svg className={styles.cardIcon} viewBox="0 0 24 24" fill="none">
                    <rect x="1" y="5" width="15" height="14" rx="2" stroke="currentColor" strokeWidth="1.8"/>
                    <circle cx="8.5" cy="12" r="3" stroke="currentColor" strokeWidth="1.8"/>
                    <circle cx="8.5" cy="12" r="1.2" fill="currentColor"/>
                    <polygon points="16,8.5 23,6 23,18 16,15.5" fill="currentColor" opacity="0.7"/>
                  </svg>
                  <span className={styles.cardLabel}>웹캠</span>
                </div>
                <span className={styles.statusBadge} style={{ color: camInfo.color }}>
                  <span className={styles.dot} style={{ background: camInfo.color }} />
                  {camInfo.label}
                </span>
              </div>

              <div className={styles.videoWrap}>
                {cameraStatus === 'granted' ? (
                  <video ref={videoRef} autoPlay muted playsInline className={styles.video} />
                ) : (
                  <div className={styles.videoPlaceholder}>
                    <svg viewBox="0 0 48 48" fill="none">
                      <rect x="4" y="10" width="32" height="28" rx="4" stroke="#ccc" strokeWidth="2"/>
                      <circle cx="20" cy="24" r="7" stroke="#ccc" strokeWidth="2"/>
                      <circle cx="20" cy="24" r="3" fill="#ccc"/>
                      <polygon points="36,16 44,12 44,36 36,32" fill="#ccc" opacity="0.6"/>
                      {cameraStatus === 'denied' && (
                        <line x1="6" y1="6" x2="42" y2="42" stroke="#f07070" strokeWidth="2.5" strokeLinecap="round"/>
                      )}
                    </svg>
                    <span>
                      {cameraStatus === 'denied'
                        ? '웹캠 권한이 거부되었습니다.\n브라우저 설정에서 허용해주세요.'
                        : '웹캠 연결을 확인 중입니다...'}
                    </span>
                  </div>
                )}
              </div>
            </div>

            {/* 마이크 섹션 */}
            <div className={styles.micCard}>
              <div className={styles.cardHeader}>
                <div className={styles.cardLabelRow}>
                  <svg className={styles.cardIcon} viewBox="0 0 24 24" fill="none">
                    <rect x="8" y="1" width="8" height="14" rx="4" stroke="currentColor" strokeWidth="1.8"/>
                    <path d="M4 11c0 4.418 3.582 8 8 8s8-3.582 8-8" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round"/>
                    <line x1="12" y1="19" x2="12" y2="23" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round"/>
                    <line x1="8"  y1="23" x2="16" y2="23" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round"/>
                  </svg>
                  <span className={styles.cardLabel}>마이크</span>
                </div>
                <span className={styles.statusBadge} style={{ color: micInfo.color }}>
                  <span className={styles.dot} style={{ background: micInfo.color }} />
                  {micInfo.label}
                </span>
              </div>

              {micStatus === 'granted' ? (
                <div className={styles.volumeWrap}>
                  {/* width=600 height=50 → CSS로 반응형 조절 */}
                  <canvas ref={canvasRef} className={styles.volumeCanvas} width={600} height={50} />
                  <span className={styles.volumeHint}>실시간 음성 입력</span>
                </div>
              ) : (
                <div className={styles.micPlaceholder}>
                  {micStatus === 'denied'
                    ? '마이크 권한이 거부되었습니다. 브라우저 설정에서 허용해주세요.'
                    : '마이크 연결을 확인 중입니다...'}
                </div>
              )}
            </div>

          </div>

          {/* 우측: 면접 준비 안내 패널 + 버튼 */}
          <div className={styles.rightColumn}>
            <aside className={styles.guidancePanel}>
              <h3 className={styles.guidanceTitle}>면접 준비 안내</h3>
              <div className={styles.guidanceList}>
                {GUIDANCE_ITEMS.map((item) => (
                  <div className={styles.guidanceItem} key={item.title}>
                    <div className={styles.guidanceItemHeader}>
                      <span className={styles.guidanceIcon}>{item.icon}</span>
                      <span className={styles.guidanceItemTitle}>{item.title}</span>
                    </div>
                    <ul className={styles.guidanceTips}>
                      {item.tips.map((tip, i) => (
                        <li key={i}>{tip}</li>
                      ))}
                    </ul>
                  </div>
                ))}
              </div>
            </aside>

            {/* 버튼: 안내 패널 아래, 마이크 영역 우측 */}
            <div className={styles.actions}>
              <button
                className={styles.startBtn}
                disabled={!allGranted}
                onClick={() => alert('면접 시작 기능은 백엔드 연결 후 구현됩니다.')}
              >
                면접 시작
              </button>
              <button className={styles.backBtn} onClick={() => navigate('/')}>
                뒤로가기
              </button>
            </div>
          </div>

        </div>{/* end mainGrid */}
      </div>
    </div>
  )
}
