import { useRef, useState, useEffect } from 'react'
import { useNavigate, useLocation } from 'react-router-dom'
import RadarChart from '../components/RadarChart'
import styles from '../styles/ResultsDetail.module.css'

function AudioPlayer({ src }) {
  const audioRef  = useRef(null)
  const [playing, setPlaying]   = useState(false)
  const [current, setCurrent]   = useState(0)
  const [duration, setDuration] = useState(0)

  useEffect(() => {
    const el = audioRef.current
    if (!el) return
    const onTime = () => setCurrent(el.currentTime)
    const onMeta = () => setDuration(el.duration || 0)
    const onEnd  = () => setPlaying(false)
    el.addEventListener('timeupdate', onTime)
    el.addEventListener('loadedmetadata', onMeta)
    el.addEventListener('ended', onEnd)
    return () => {
      el.removeEventListener('timeupdate', onTime)
      el.removeEventListener('loadedmetadata', onMeta)
      el.removeEventListener('ended', onEnd)
    }
  }, [])

  const toggle = () => {
    const el = audioRef.current
    if (!el) return
    if (playing) { el.pause(); setPlaying(false) }
    else         { el.play();  setPlaying(true)  }
  }

  const seek = (e) => {
    const el = audioRef.current
    if (!el || !duration) return
    const rect = e.currentTarget.getBoundingClientRect()
    el.currentTime = ((e.clientX - rect.left) / rect.width) * duration
  }

  const fmt = (s) => {
    const m = Math.floor(s / 60), sec = Math.floor(s % 60)
    return `${String(m).padStart(2,'0')}:${String(sec).padStart(2,'0')}`
  }

  const pct = duration ? (current / duration) * 100 : 0

  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 8, width: '100%', marginTop: 4 }}>
      <audio ref={audioRef} preload="metadata" src={src} />
      <button onClick={toggle} style={{
        width: 28, height: 28, borderRadius: '50%', border: 'none',
        background: '#50eba0', color: '#fff', cursor: 'pointer',
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        flexShrink: 0, fontSize: 10,
      }}>
        {playing ? '⏸' : '▶'}
      </button>
      <div onClick={seek} style={{
        flex: 1, height: 4, background: '#ddd', borderRadius: 2,
        cursor: 'pointer', position: 'relative',
      }}>
        <div style={{
          width: `${pct}%`, height: '100%',
          background: 'linear-gradient(90deg, #50eba0, #5BB8F5)',
          borderRadius: 2, transition: 'width 0.1s linear',
        }} />
      </div>
      <span style={{ fontSize: 11, color: '#aaa', flexShrink: 0, minWidth: 36 }}>
        {fmt(current)}
      </span>
    </div>
  )
}

function PanelLogo() {
  const navigate = useNavigate()
  return (
    <button
      onClick={() => navigate('/')}
      aria-label="홈으로 이동"
      style={{
        background: 'none', border: 'none', padding: '0 0 4px',
        cursor: 'pointer', display: 'flex', alignItems: 'center',
      }}
    >
      <img src="/logo.png" alt="PreView" style={{ height: 40, width: 'auto', objectFit: 'contain' }} />
    </button>
  )
}

const SCORE_LABELS = [
  { key: '표정안정성',   label: '표정 안정성',   color: '#50eba0' },
  { key: '표정다양성',   label: '표정 다양성',   color: '#5BB8F5' },
  { key: '자세안정성',   label: '자세 안정성',   color: '#50eba0' },
  { key: '시선처리',     label: '시선 처리',     color: '#5BB8F5' },
  { key: '발화속도',     label: '발화 속도',     color: '#50eba0' },
  { key: '말하기안정성', label: '말하기 안정성', color: '#5BB8F5' },
]

function getGrade(score) {
  if (score == null) return { text: '대기 중', color: '#aaa' }
  if (score >= 90)   return { text: '매우 우수', color: '#50eba0' }
  if (score >= 75)   return { text: '우수',     color: '#5BB8F5' }
  if (score >= 60)   return { text: '보통',     color: '#f5b942' }
  return                    { text: '개선 필요', color: '#f07070' }
}

function formatTime(sec) {
  if (sec == null) return '--:--'
  const m = Math.floor(sec / 60)
  const s = Math.floor(sec % 60)
  return `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`
}

// ── 문장 단위 감점 이벤트 그룹핑 ────────────────────────────────────────────

function groupSpeechEvents(events, gapSec = 5.0) {
  if (!events.length) return []
  const sorted = [...events].sort((a, b) => (a.startSec ?? 0) - (b.startSec ?? 0))
  const groups = []
  let cur = {
    descs: [sorted[0].desc],
    timestamp: sorted[0].timestamp,
    startSec: sorted[0].startSec,
    endSec: sorted[0].endSec,
  }
  for (let i = 1; i < sorted.length; i++) {
    const d = sorted[i]
    if ((d.startSec ?? 0) - (cur.endSec ?? 0) <= gapSec) {
      cur.descs.push(d.desc)
      cur.endSec = Math.max(cur.endSec ?? 0, d.endSec ?? 0)
    } else {
      groups.push(cur)
      cur = { descs: [d.desc], timestamp: d.timestamp, startSec: d.startSec, endSec: d.endSec }
    }
  }
  groups.push(cur)
  return groups
}

// ── 오디오 클립 재생 가능한 감점 구간 카드 (문장 단위) ───────────────────────

function summarizeDescs(descs) {
  const counts = {}
  for (const d of descs) counts[d] = (counts[d] || 0) + 1
  return Object.entries(counts)
    .map(([text, cnt]) => cnt > 1 ? text.replace(' 감지', ` ${cnt}회 감지`) : text)
    .join(' · ')
}

function AudioClipCard({ timestamp, descs, jobId, startSec, endSec }) {
  const clipUrl = jobId != null && startSec != null && endSec != null
    ? `/api/audio-clip/${jobId}?start=${startSec.toFixed(2)}&end=${endSec.toFixed(2)}`
    : null

  return (
    <div className={styles.clipItem}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
        <span className={styles.timestamp}>{timestamp}</span>
        <svg viewBox="0 0 48 16" fill="none" style={{ width: 36, flexShrink: 0 }}>
          <rect x="0"  y="6" width="2" height="4"  rx="1" fill="#50eba0"/>
          <rect x="4"  y="3" width="2" height="10" rx="1" fill="#50eba0"/>
          <rect x="8"  y="1" width="2" height="14" rx="1" fill="#5BB8F5"/>
          <rect x="12" y="4" width="2" height="8"  rx="1" fill="#50eba0"/>
          <rect x="16" y="2" width="2" height="12" rx="1" fill="#5BB8F5"/>
          <rect x="20" y="5" width="2" height="6"  rx="1" fill="#50eba0"/>
          <rect x="24" y="3" width="2" height="10" rx="1" fill="#5BB8F5"/>
          <rect x="28" y="6" width="2" height="4"  rx="1" fill="#50eba0"/>
          <rect x="32" y="4" width="2" height="8"  rx="1" fill="#5BB8F5"/>
          <rect x="36" y="2" width="2" height="12" rx="1" fill="#50eba0"/>
          <rect x="40" y="5" width="2" height="6"  rx="1" fill="#5BB8F5"/>
          <rect x="44" y="3" width="2" height="10" rx="1" fill="#50eba0"/>
        </svg>
        <span className={styles.clipDesc}>{summarizeDescs(descs)}</span>
      </div>
      {clipUrl && <AudioPlayer src={clipUrl} />}
    </div>
  )
}

function CorrectionImageSlot({ url }) {
  return (
    <div className={styles.correctionImageSlot}>
      {url
        ? <img src={url} alt="교정 제안 이미지" className={styles.correctionImage} />
        : <div className={styles.correctionImagePlaceholder}>
            <svg viewBox="0 0 40 40" fill="none">
              <rect x="2" y="2" width="36" height="36" rx="6" stroke="#ccc" strokeWidth="1.5" strokeDasharray="4 3"/>
              <path d="M20 14v12M14 20h12" stroke="#ccc" strokeWidth="2" strokeLinecap="round"/>
            </svg>
            <span>교정 제안 이미지<br/>(이미지 생성 모델 연결 후 표시)</span>
          </div>
      }
    </div>
  )
}

function PendingSection({ title, color }) {
  return (
    <section className={styles.section}>
      <h3 className={styles.sectionTitle}>
        <span className={styles.sectionDot} style={{ background: color }} />
        {title}
      </h3>
      <div style={{
        padding: '24px 0', textAlign: 'center',
        color: '#aaa', fontSize: 14,
        border: '1.5px dashed #e0e0e0', borderRadius: 12,
      }}>
        비언어모듈 연결 후 표시됩니다
      </div>
    </section>
  )
}

export default function ResultsDetail() {
  const navigate    = useNavigate()
  const location    = useLocation()
  const compareData = location.state?.compareData || null

  const jobId              = compareData?.current?.job_id || null
  const scores             = compareData?.current?.scores || {}
  const lang               = compareData?.current?.language_analysis || {}
  const metrics            = lang.metrics || {}
  const raw                = lang.raw_data || {}
  const answers            = compareData?.current?.answers || []
  const displayTranscript  = compareData?.current?.corrected_transcript || raw.transcript || ''

  const radarValues  = SCORE_LABELS.map(({ key }) => scores[key] ?? 0)
  const validScores  = SCORE_LABELS.map(({ key }) => scores[key]).filter(v => v != null)
  const avg          = validScores.length > 0
    ? Math.round(validScores.reduce((a, b) => a + b, 0) / validScores.length)
    : null
  const avgGrade = getGrade(avg)

  // ── 언어 분석 데이터 ─────────────────────────────────────────────────────
  const speechRate = metrics.speech_rate     || {}
  const fillers    = metrics.filler_word     || { count: 0, occurrences: [] }
  const stutters   = metrics.stuttering      || { count: 0, occurrences: [] }
  const pauses     = metrics.long_pauses     || { count: 0, occurrences: [] }
  const volume     = metrics.volume_stability || {}

  // 습관어 집계 (단어별 횟수)
  const fillerMap = {}
  for (const occ of fillers.occurrences) {
    const w = occ.word || ''
    fillerMap[w] = (fillerMap[w] || 0) + 1
  }
  const fillerWords = Object.entries(fillerMap)
    .sort((a, b) => b[1] - a[1])
    .map(([word, count]) => ({ word, count }))

  // 습관어·더듬음 감점 구간 (최대 8개, 시간순)
  const speechDeductions = [
    ...fillers.occurrences.map(occ => ({
      timestamp: formatTime(occ.time),
      desc:      `습관어 "${occ.word}" 감지`,
      startSec:  Math.max(0, (occ.time ?? 0) - 0.5),
      endSec:    (occ.time ?? 0) + 1.5,
    })),
    ...stutters.occurrences.map(occ => ({
      timestamp: formatTime(occ.time),
      desc:      `더듬음 "${occ.word}" 감지`,
      startSec:  Math.max(0, (occ.time ?? 0) - 0.5),
      endSec:    (occ.time ?? 0) + 1.5,
    })),
  ].sort((a, b) => a.timestamp.localeCompare(b.timestamp)).slice(0, 8)

  // 긴 침묵 감점 구간 (최대 5개)
  const pauseDeductions = pauses.occurrences.slice(0, 5).map(occ => ({
    timestamp: formatTime(occ.start),
    desc:      `긴 침묵 ${(occ.duration ?? (occ.end - occ.start)).toFixed(1)}초`,
    startSec:  Math.max(0, (occ.start ?? 0) - 0.3),
    endSec:    (occ.end ?? occ.start + 2) + 0.3,
  }))

  const hasLangData = lang.status === 'success'

  // ── 항목별 교정 제안 ──────────────────────────────────────────────────────
  const spmVal = speechRate.spm
  const speechRateSuggestions = []
  if (spmVal != null && spmVal > 350)  speechRateSuggestions.push(`발화 속도가 빠릅니다 (${Math.round(spmVal)} spm). 의도적으로 천천히 말하는 연습을 해보세요.`)
  if (spmVal != null && spmVal < 270)  speechRateSuggestions.push(`발화 속도가 느립니다 (${Math.round(spmVal)} spm). 답변을 미리 준비해 자신감 있게 말해보세요.`)
  if (pauses.count > 2)                speechRateSuggestions.push(`긴 침묵이 ${pauses.count}회 감지되었습니다. 답변 구조화 후 핵심부터 말하는 연습이 도움됩니다.`)
  if (!speechRateSuggestions.length)   speechRateSuggestions.push('발화 속도와 흐름이 안정적입니다.')

  const stabilitySuggestions = []
  if (fillers.count > 3)               stabilitySuggestions.push(`습관어가 ${fillers.count}회 사용되었습니다. 말하기 전 짧은 침묵(1~2초)으로 대체해보세요.`)
  if (stutters.count > 0)              stabilitySuggestions.push(`더듬음이 ${stutters.count}회 감지되었습니다. 천천히, 자신감 있게 말하는 연습이 도움이 됩니다.`)
  if (volume.is_loud_enough === false)  stabilitySuggestions.push('음량이 너무 작습니다. 면접관이 잘 들을 수 있도록 목소리를 키워보세요.')
  if (volume.is_stable === false)       stabilitySuggestions.push('음량이 불안정합니다. 일정한 호흡으로 말하는 연습을 해보세요.')
  if (!stabilitySuggestions.length)    stabilitySuggestions.push('습관어·더듬음·음량 모두 안정적입니다.')

  return (
    <div className={styles.pageLayout}>

      {/* ════ 좌측 패널: 레이더 차트 (고정) ════ */}
      <aside className={styles.leftPanel}>
        <div className={styles.leftInner}>
          <PanelLogo />
          <h2 className={styles.leftTitle}>분석 결과</h2>

          <div className={styles.avgBadge}>
            <span className={styles.avgScore}>{avg != null ? `${avg}점` : '집계 중'}</span>
            <span className={styles.avgGrade} style={{ color: avgGrade.color }}>{avgGrade.text}</span>
          </div>

          <div className={styles.chartWrap}>
            <RadarChart scores={radarValues} />
          </div>

          <div className={styles.scoreList}>
            {SCORE_LABELS.map(({ key, label, color }) => {
              const score = scores[key] ?? null
              const grade = getGrade(score)
              return (
                <div className={styles.scoreRow} key={key}>
                  <span className={styles.scoreLabel}>{label}</span>
                  <div className={styles.scoreTrack}>
                    {score != null ? (
                      <div className={styles.scoreFill} style={{ width: `${score}%`, background: color }} />
                    ) : (
                      <div className={styles.scoreFill} style={{ width: '100%', background: '#eee' }} />
                    )}
                  </div>
                  <span className={styles.scoreNum}>{score != null ? score : '—'}</span>
                  <span className={styles.scoreGrade} style={{ color: grade.color }}>{grade.text}</span>
                </div>
              )
            })}
          </div>

          <div className={`${styles.leftActions} ${styles.printHide}`}>
            <button className={styles.pdfBtn} onClick={() => window.print()}>
              <svg viewBox="0 0 20 20" fill="none">
                <path d="M6 2h8l4 4v12H2V2h4z" stroke="currentColor" strokeWidth="1.5"/>
                <path d="M6 2v4h8V2" stroke="currentColor" strokeWidth="1.5"/>
                <path d="M6 12h8M6 15h5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/>
              </svg>
              PDF로 저장
            </button>
            <button className={styles.homeBtn} onClick={() => navigate('/')}>처음으로</button>
          </div>
        </div>
      </aside>

      {/* ════ 우측 패널: 상세 분석 (스크롤) ════ */}
      <main className={styles.rightPanel}>
        <h2 className={styles.rightTitle}>상세 분석 결과</h2>

        {/* ── 표정 분석 (비언어모듈 대기) ── */}
        <PendingSection title="표정 분석" color="#50eba0" />

        {/* ── 자세 분석 (비언어모듈 대기) ── */}
        <PendingSection title="자세 분석" color="#5BB8F5" />

        {/* ── 말하기 분석 ── */}
        <section className={styles.section}>
          <h3 className={styles.sectionTitle}>
            <span className={styles.sectionDot} style={{ background: '#50eba0' }} />
            말하기 분석
          </h3>

          {!hasLangData ? (
            <div style={{ padding: '24px 0', textAlign: 'center', color: '#aaa', fontSize: 14 }}>
              언어 분석 데이터를 불러올 수 없습니다.
            </div>
          ) : (
            <>
              {/* 요약 수치 */}
              <div className={styles.statsRow}>
                {[
                  { label: '발화 속도 점수', val: `${scores['발화속도'] ?? '—'}점` },
                  { label: '속도 평가',      val: speechRate.label || '—',   color: '#50eba0' },
                  { label: '분당 음절 수',   val: speechRate.spm != null ? `${Math.round(speechRate.spm)} spm` : '—' },
                  { label: '습관어 횟수',    val: `${fillers.count}회` },
                  { label: '더듬음 횟수',    val: `${stutters.count}회` },
                  { label: '긴 침묵 횟수',   val: `${pauses.count}회` },
                  { label: '음량 상태',      val: volume.label || '—', color: (volume.label === '작음' || volume.label === '너무 작음') ? '#f07070' : volume.is_stable ? '#50eba0' : undefined },
                ].map(s => (
                  <div className={styles.statCard} key={s.label}>
                    <span className={styles.statLabel}>{s.label}</span>
                    <span className={styles.statValue} style={s.color ? { color: s.color } : {}}>{s.val}</span>
                  </div>
                ))}
              </div>


              {/* 답변별 발화 속도 (2개 이상일 때) */}
              {answers.length > 1 && (
                <div style={{ marginBottom: 20 }}>
                  <p className={styles.subLabel}>답변별 발화 속도</p>
                  <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
                    {answers.map((ans, i) => {
                      const spm   = ans.language_analysis?.metrics?.speech_rate?.spm
                      const label = ans.language_analysis?.metrics?.speech_rate?.label
                      const color = label === '적절' ? '#50eba0' : label === '빠름' ? '#f07070' : '#f5b942'
                      return (
                        <div key={i} style={{
                          padding: '6px 12px', borderRadius: 8,
                          background: color + '22', border: `1px solid ${color}`,
                          fontSize: 13,
                        }}>
                          <span style={{ color: '#666' }}>답변 {i + 1}</span>
                          <span style={{ color, fontWeight: 700, marginLeft: 6 }}>
                            {spm != null ? `${Math.round(spm)} spm` : '—'} {label ? `(${label})` : ''}
                          </span>
                        </div>
                      )
                    })}
                  </div>
                </div>
              )}

              {/* 습관어 빈도 */}
              {fillers.count > 0 && (
                <div className={styles.fillerWords}>
                  <p className={styles.subLabel}>습관어 빈도 (총 {fillers.count}회)</p>
                  <div className={styles.fillerGrid}>
                    {fillerWords.map(f => (
                      <div className={styles.fillerItem} key={f.word}>
                        <span className={styles.fillerWord}>"{f.word}"</span>
                        <span className={styles.fillerCount}>{f.count}회</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* 습관어·더듬음 감점 구간 — 문장 단위로 묶어 클립 1개 */}
              {speechDeductions.length > 0 && (
                <div className={styles.deductionList}>
                  <p className={styles.subLabel}>습관어·더듬음 구간 (클립 재생 가능)</p>
                  <div className={styles.clips}>
                    {groupSpeechEvents(speechDeductions).map((g, i) => (
                      <AudioClipCard
                        key={i}
                        timestamp={g.timestamp}
                        descs={g.descs}
                        jobId={jobId}
                        startSec={Math.max(0, (g.startSec ?? 0) - 0.5)}
                        endSec={(g.endSec ?? 0) + 1.5}
                      />
                    ))}
                  </div>
                </div>
              )}

              {/* 긴 침묵 구간 — 타임스탬프만 표시 (무음 구간이라 클립 불필요) */}
              {pauseDeductions.length > 0 && (
                <div className={styles.deductionList}>
                  <p className={styles.subLabel}>긴 침묵 구간</p>
                  <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
                    {pauseDeductions.map((d, i) => (
                      <div key={i} style={{
                        padding: '6px 12px', borderRadius: 8,
                        background: '#f5f5f5', border: '1px solid #e0e0e0',
                        fontSize: 13, color: '#555',
                      }}>
                        <span style={{ fontWeight: 700, color: '#f5b942', marginRight: 6 }}>
                          {d.timestamp}
                        </span>
                        {d.desc}
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* 인식된 발화 텍스트 — 화자 2명 이상이면 답변별 Q&A 구조로 표시 */}
              {(displayTranscript || answers.length > 0) && (
                <div className={styles.suggestionBox}>
                  <p className={styles.subLabel}>인식된 발화 텍스트</p>

                  {answers.length > 1 ? (
                    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
                      {answers.map((ans, i) => {
                        const transcript = ans.language_analysis?.raw_data?.transcript || ''
                        const question   = ans.question || ''
                        return (
                          <div key={i}>
                            {question && (
                              <div style={{
                                fontSize: 13, color: '#5BB8F5', fontWeight: 600,
                                marginBottom: 6, paddingLeft: 4,
                              }}>
                                Q. {question}
                              </div>
                            )}
                            <div style={{ borderLeft: '3px solid #50eba0', paddingLeft: 12 }}>
                              <span style={{ fontSize: 12, fontWeight: 700, color: '#50eba0' }}>
                                답변 {i + 1} &nbsp;
                                <span style={{ fontWeight: 400, color: '#aaa' }}>
                                  [{formatTime(ans.start)} ~ {ans.end != null ? formatTime(ans.end) : '끝'}]
                                </span>
                              </span>
                              <p className={styles.llmText}
                                 style={{ whiteSpace: 'pre-wrap', lineHeight: 1.7, margin: '4px 0 0' }}>
                                {transcript || '(전사 없음)'}
                              </p>
                            </div>
                          </div>
                        )
                      })}
                    </div>
                  ) : (
                    <p className={styles.llmText} style={{ whiteSpace: 'pre-wrap', lineHeight: 1.7 }}>
                      {displayTranscript}
                    </p>
                  )}
                </div>
              )}

              {/* 교정 제안 — 항목별 */}
              <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
                {/* 발화속도 — 파랑 */}
                <div className={styles.suggestionBox} style={{ borderLeftColor: '#5BB8F5', background: '#f0f7ff' }}>
                  <p className={styles.subLabel} style={{ color: '#5BB8F5' }}>발화속도</p>
                  <ul style={{ margin: 0, padding: '0 0 0 18px', display: 'flex', flexDirection: 'column', gap: 4 }}>
                    {speechRateSuggestions.map((s, i) => (
                      <li key={i} className={styles.llmText} style={{ margin: 0 }}>{s}</li>
                    ))}
                  </ul>
                </div>
                {/* 말하기 안정성 — 초록 */}
                <div className={styles.suggestionBox}>
                  <p className={styles.subLabel} style={{ color: '#50eba0' }}>말하기 안정성</p>
                  <ul style={{ margin: 0, padding: '0 0 0 18px', display: 'flex', flexDirection: 'column', gap: 4 }}>
                    {stabilitySuggestions.map((s, i) => (
                      <li key={i} className={styles.llmText} style={{ margin: 0 }}>{s}</li>
                    ))}
                  </ul>
                </div>
              </div>
            </>
          )}
        </section>
      </main>
    </div>
  )
}
