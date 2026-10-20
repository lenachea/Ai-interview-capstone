import { useRef, useState, useEffect } from 'react'
import { useNavigate, useLocation } from 'react-router-dom'
import RadarChart from '../components/RadarChart'
import ComparisonChart from '../components/ComparisonChart'
import ScoreTrendChart from '../components/ScoreTrendChart'
import styles from '../styles/ResultsDetail.module.css'
import { getHistory, getRealtimeVideoUrl } from '../lib/api'

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
  { key: '발화속도',   label: '발화 속도',    color: '#50eba0' },
  { key: '음성명확성', label: '음성 명확성',  color: '#5BB8F5' },
  { key: '유창성침묵', label: '유창성·침묵',  color: '#50eba0' },
  { key: '습관어',     label: '습관어',       color: '#5BB8F5' },
  { key: '시선처리',   label: '시선 처리',    color: '#50eba0' },
  { key: '표정안정성', label: '표정 안정성',  color: '#5BB8F5' },
  { key: '자세안정성', label: '자세 안정성',  color: '#50eba0' },
]

function getOverallScore(record) {
  const scores = record?.scores || {}
  const values = SCORE_LABELS
    .map(({ key }) => scores[key])
    .filter(value => typeof value === 'number' && Number.isFinite(value))
  if (!values.length) return null
  return Math.round(values.reduce((sum, value) => sum + value, 0) / values.length)
}

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

function FrameInline({ jobId, t, label, onClose }) {
  const src = jobId != null && t != null ? `/api/frame/${jobId}?t=${t.toFixed(2)}` : null

  return (
    <div style={{
      marginBottom: 16, padding: 12, borderRadius: 12,
      background: '#fafafa', border: '1px solid #eee',
      display: 'flex', flexDirection: 'column', gap: 8,
    }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', width: '100%' }}>
        <span style={{ fontSize: 13, fontWeight: 700, color: '#333' }}>{label}</span>
        <button
          onClick={onClose}
          style={{
            border: 'none', background: '#eee', borderRadius: 6,
            width: 22, height: 22, cursor: 'pointer', fontSize: 12, color: '#666',
          }}
        >
          ✕
        </button>
      </div>

      {src && <img src={src} alt={label} style={{ width: 420, maxWidth: '100%', borderRadius: 8, display: 'block' }} />}
    </div>
  )
}

const REFERENCE_LABELS = {
  expression: '표정',
  gaze: '시선',
  posture: '자세',
}

function representativeProblems(group, deductions) {
  const sorted = [...deductions].sort((a, b) => {
    if (group === 'posture') return (b.confidence ?? 0) - (a.confidence ?? 0)
    return ((b.end ?? b.start) - b.start) - ((a.end ?? a.start) - a.start)
  })
  const selected = []
  for (const item of sorted) {
    const t = group === 'posture'
      ? (item.sec ?? 0)
      : ((item.start ?? 0) + (item.end ?? item.start ?? 0)) / 2
    if (selected.every(existing => Math.abs(existing.t - t) >= 1.5)) selected.push({ ...item, t })
    if (selected.length === 2) break
  }
  return selected
}

function ReferenceComparison({ jobId, group, deductions }) {
  const [open, setOpen] = useState(false)
  const [imageState, setImageState] = useState('loading')
  const problems = representativeProblems(group, deductions)
  if (!jobId || !problems.length) return null

  const toggle = () => {
    if (!open) setImageState('loading')
    setOpen(value => !value)
  }

  return (
    <div style={{ margin: '10px 0 20px' }}>
      <button onClick={toggle} style={{
        padding: '8px 14px', borderRadius: 8, border: '1px solid #5BB8F5',
        background: open ? '#eaf4ff' : '#fff', color: '#2a7fc9', fontWeight: 700,
        cursor: 'pointer', fontSize: 13,
      }}>
        {open ? '개선 레퍼런스 닫기' : `${REFERENCE_LABELS[group]} 개선 레퍼런스 이미지 보기`}
      </button>

      {open && (
        <div style={{
          display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))',
          gap: 12, marginTop: 12, padding: 12, border: '1px solid #e5e5e5', borderRadius: 12,
          background: '#fafafa',
        }}>
          {problems.map((problem, index) => (
            <div key={problem.t}>
              <p style={{ margin: '0 0 6px', fontSize: 12, color: '#f07070', fontWeight: 700 }}>
                {problem.representative ? '대표 자세 장면' : '대표 문제 장면'} {index + 1} · {formatTime(problem.t)}
              </p>
              <img
                src={`/api/frame/${jobId}?t=${problem.t.toFixed(2)}`}
                alt={`${REFERENCE_LABELS[group]} 대표 문제 장면 ${index + 1}`}
                style={{ width: '100%', borderRadius: 8, display: 'block' }}
              />
            </div>
          ))}
          <div>
            <p style={{ margin: '0 0 6px', fontSize: 12, color: '#3d9d70', fontWeight: 700 }}>
              개선 레퍼런스 <span style={{ color: '#aaa', fontWeight: 400 }}>AI 생성</span>
            </p>
            {imageState === 'loading' && (
              <div style={{
                aspectRatio: '16 / 9', borderRadius: 8, background: '#eef7f2',
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                color: '#6aa58a', fontSize: 12, textAlign: 'center', padding: 12,
              }}>
                대표 문제 장면 {problems.length}개를 바탕으로<br />개선 이미지를 만드는 중입니다...
              </div>
            )}
            {imageState === 'error' && (
              <div style={{ padding: 20, borderRadius: 8, background: '#fff5f5', color: '#f07070', fontSize: 12 }}>
                개선 이미지를 생성하지 못했습니다. 잠시 후 다시 열어주세요.
              </div>
            )}
            <img
              src={`/api/improvement-reference/${jobId}/${group}`}
              alt={`${REFERENCE_LABELS[group]} 개선 레퍼런스`}
              onLoad={() => setImageState('ready')}
              onError={() => setImageState('error')}
              style={{ width: '100%', borderRadius: 8, display: imageState === 'ready' ? 'block' : 'none' }}
            />
          </div>
        </div>
      )}
    </div>
  )
}

function EvidenceCard({ point, evidence, color = '#5BB8F5' }) {
  return (
    <div style={{ borderLeft: `3px solid ${color}`, paddingLeft: 10, marginBottom: 8 }}>
      <p className={styles.llmText} style={{ margin: 0, fontWeight: 600 }}>{point}</p>
      {evidence && <p className={styles.llmText} style={{ margin: '2px 0 0', color: '#888', fontSize: 13 }}>{evidence}</p>}
    </div>
  )
}

function ReportState({ status, onRetry }) {
  if (status === 'loading' || status === 'idle') {
    return <p className={styles.llmText} style={{ color: '#888' }}>측정된 면접 태도를 바탕으로 분석을 작성하고 있습니다...</p>
  }
  if (status === 'error') {
    return (
      <p className={styles.llmText} style={{ color: '#f07070' }}>
        분석을 불러오지 못했습니다.
        <button onClick={onRetry} style={{ marginLeft: 8, border: 0, background: 'none', color: '#5BB8F5', cursor: 'pointer' }}>다시 시도</button>
      </p>
    )
  }
  return null
}

function QuestionAnalysis({ report, modality, color }) {
  const questions = report?.per_question || []
  if (!questions.length) return null
  return (
    <div style={{ marginTop: 18 }}>
      <p className={styles.subLabel} style={{ color, fontSize: 15, marginBottom: 8 }}>질문별 정밀 분석</p>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
        {questions.map((question, index) => {
          const analysis = question[modality] || {}
          return (
            <div key={question.index ?? index} style={{ border: '1px solid #eee', borderRadius: 12, padding: 14 }}>
              <p style={{ fontWeight: 700, color: '#333', margin: '0 0 4px' }}>Q{index + 1}. {question.question_label}</p>
              <p style={{ fontSize: 12, color: '#aaa', margin: '0 0 8px' }}>
                {formatTime(question.start_sec)} ~ {formatTime(question.end_sec)} 구간
              </p>
              {analysis.summary && <p className={styles.llmText}>{analysis.summary}</p>}
              {analysis.strengths?.length > 0 && (
                <ul style={{ margin: '8px 0 0', paddingLeft: 18 }}>
                  {analysis.strengths.map((item, i) => <li key={i} className={styles.llmText} style={{ color: '#3d8d68' }}>{item}</li>)}
                </ul>
              )}
              {analysis.improvements?.length > 0 && (
                <ul style={{ margin: '8px 0 0', paddingLeft: 18 }}>
                  {analysis.improvements.map((item, i) => <li key={i} className={styles.llmText} style={{ color: '#b27720' }}>{item}</li>)}
                </ul>
              )}
            </div>
          )
        })}
      </div>
    </div>
  )
}

function VisionDeepAnalysis({ report }) {
  const overview = report?.modality_analysis?.vision
  return (
    <div style={{ marginTop: 18 }}>
      {overview && (
        <div className={styles.suggestionBox} style={{ borderLeftColor: '#5BB8F5', background: '#f0f7ff' }}>
          <p className={styles.subLabel} style={{ color: '#5BB8F5' }}>평가된 비전 특징 분석</p>
          <p className={styles.llmText}>{overview}</p>
        </div>
      )}
      <QuestionAnalysis report={report} modality="vision" color="#5BB8F5" />
    </div>
  )
}

function VoiceDeepAnalysis({ report }) {
  const overview = report?.modality_analysis?.voice
  return (
    <div style={{ marginTop: 18 }}>
      {overview && (
        <div className={styles.suggestionBox} style={{ borderLeftColor: '#50eba0', background: '#f0fff8' }}>
          <p className={styles.subLabel} style={{ color: '#3d9d70' }}>평가된 음성 특징 분석</p>
          <p className={styles.llmText}>{overview}</p>
        </div>
      )}
      <QuestionAnalysis report={report} modality="voice" color="#3d9d70" />
    </div>
  )
}

function InterviewComparison({ current, previous, diff }) {
  if (!previous) {
    return (
      <div style={{ padding: '24px', textAlign: 'center', color: '#888', background: '#fafafa', borderRadius: 12 }}>
        아직 비교할 이전 기록이 없습니다.<br />다음 면접부터 좋아진 점과 달라진 흐름을 함께 보여드릴게요.
      </div>
    )
  }

  const comparable = SCORE_LABELS
    .map(item => {
      const currentScore = current?.scores?.[item.key]
      const previousScore = previous?.scores?.[item.key]
      return {
        ...item,
        current: currentScore,
        previous: previousScore,
        change: diff?.[item.key] ?? (
          currentScore != null && previousScore != null ? currentScore - previousScore : null
        ),
      }
    })
    .filter(item => item.current != null && item.previous != null)

  if (!comparable.length) {
    return <p className={styles.llmText} style={{ color: '#888' }}>두 기록에서 함께 비교할 수 있는 항목이 없습니다.</p>
  }

  const improved = comparable.filter(item => item.change > 1).sort((a, b) => b.change - a.change)
  const declined = comparable.filter(item => item.change < -1).sort((a, b) => a.change - b.change)
  const steady = comparable
    .filter(item => Math.abs(item.change ?? 0) <= 1)
    .sort((a, b) => b.current - a.current)

  const names = items => items.slice(0, 3).map(item => item.label).join(', ')
  const improvedText = improved.length
    ? `${names(improved)}에서 이전보다 더 안정된 모습을 보였습니다. 특히 ${improved[0].label}의 변화가 가장 뚜렷합니다.`
    : '이전보다 뚜렷하게 좋아진 항목은 아직 없지만, 큰 흔들림 없이 유지한 부분을 다음 연습의 기반으로 삼을 수 있습니다.'
  const declinedText = declined.length
    ? `${names(declined)}은 이전보다 다소 흔들렸습니다. 다음 연습에서는 ${declined[0].label}부터 집중해서 확인해보세요.`
    : '이전보다 눈에 띄게 나빠진 항목은 없습니다. 현재의 말하기와 비언어 태도를 그대로 유지해보세요.'
  const steadyText = steady.length
    ? `${names(steady)}은 이전과 비슷한 수준을 유지했습니다. 급하게 바꾸기보다 지금의 안정감을 이어가는 것이 좋습니다.`
    : '이번에는 여러 항목에서 변화가 나타났습니다. 한꺼번에 교정하기보다 변화가 큰 항목부터 하나씩 다듬어보세요.'

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 18 }}>
      <div style={{ padding: '12px 8px 4px' }}>
        <ComparisonChart
          labels={comparable.map(item => item.label)}
          currentScores={comparable.map(item => item.current)}
          previousScores={comparable.map(item => item.previous)}
        />
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(230px, 1fr))', gap: 10 }}>
        <div className={styles.suggestionBox} style={{ borderLeftColor: '#50eba0', background: '#f0fff8' }}>
          <p className={styles.subLabel} style={{ color: '#3d9d70' }}>좋아진 점</p>
          <p className={styles.llmText}>{improvedText}</p>
        </div>
        <div className={styles.suggestionBox} style={{ borderLeftColor: '#f5b942', background: '#fffdf5' }}>
          <p className={styles.subLabel} style={{ color: '#b27720' }}>조금 더 신경 쓸 점</p>
          <p className={styles.llmText}>{declinedText}</p>
        </div>
        <div className={styles.suggestionBox} style={{ borderLeftColor: '#5BB8F5', background: '#f0f7ff' }}>
          <p className={styles.subLabel} style={{ color: '#2a7fc9' }}>꾸준히 유지된 점</p>
          <p className={styles.llmText}>{steadyText}</p>
        </div>
      </div>
    </div>
  )
}

function OverallReportView({ report }) {
  const summary = report.executive_summary || {}
  const patterns = report.behavior_pattern_analysis || {}
  const competency = report.competency_assessment || {}
  const priorities = report.priority_improvements || []
  const plan = report.training_plan || []
  const competencyRows = [
    ['비전 분석', competency.vision, '#5BB8F5'],
    ['음성 분석', competency.voice, '#50eba0'],
  ]
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
      <div>
        <p className={styles.subLabel} style={{ color: '#5BB8F5', fontSize: 15 }}>종합 면접 진단</p>
        <div className={styles.suggestionBox} style={{ borderLeftColor: '#5BB8F5', background: '#f0f7ff', marginTop: 8 }}>
          <p className={styles.llmText}>{summary.overall_evaluation}</p>
          {summary.priority_area && <p className={styles.llmText} style={{ marginTop: 8 }}><b>가장 먼저 바꿀 점</b> — {summary.priority_area}</p>}
        </div>
        <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap', marginTop: 10 }}>
          <div style={{ flex: '1 1 260px', background: '#f0fff8', borderRadius: 10, padding: 12 }}>
            <p className={styles.subLabel} style={{ color: '#3d9d70' }}>핵심 강점</p>
            {(summary.key_strengths || []).map((item, i) => <EvidenceCard key={i} {...item} color="#50eba0" />)}
          </div>
          <div style={{ flex: '1 1 260px', background: '#fff5f5', borderRadius: 10, padding: 12 }}>
            <p className={styles.subLabel} style={{ color: '#f07070' }}>우선 보완점</p>
            {(summary.key_weaknesses || []).map((item, i) => <EvidenceCard key={i} {...item} color="#f07070" />)}
          </div>
        </div>
      </div>

      {(patterns.patterns?.length > 0 || patterns.note) && (
        <div>
          <p className={styles.subLabel} style={{ color: '#5BB8F5', fontSize: 15 }}>면접 행동 패턴 종합 진단</p>
          {(patterns.patterns || []).map((pattern, i) => (
            <div key={i} className={styles.suggestionBox} style={{ borderLeftColor: '#5BB8F5', marginTop: 8 }}>
              <p className={styles.llmText} style={{ fontWeight: 600 }}>{pattern.observation}</p>
              {pattern.evidence && <p className={styles.llmText} style={{ color: '#777', fontSize: 13 }}>근거: {pattern.evidence}</p>}
              {pattern.coaching && <p className={styles.llmText} style={{ marginTop: 4 }}>{pattern.coaching}</p>}
            </div>
          ))}
          {patterns.note && <p className={styles.llmText} style={{ color: '#888', marginTop: 8 }}>{patterns.note}</p>}
        </div>
      )}

      <div>
        <p className={styles.subLabel} style={{ color: '#5BB8F5', fontSize: 15 }}>역량별 심층 평가</p>
        {competencyRows.map(([label, text, color]) => text && (
          <div key={label} className={styles.suggestionBox} style={{ borderLeftColor: color, marginTop: 8 }}>
            <p className={styles.subLabel} style={{ color }}>{label}</p>
            <p className={styles.llmText}>{text}</p>
          </div>
        ))}
      </div>

      {priorities.length > 0 && (
        <div>
          <p className={styles.subLabel} style={{ color: '#f5b942', fontSize: 15 }}>핵심 개선 과제</p>
          {priorities.map((item, i) => (
            <div key={i} className={styles.suggestionBox} style={{ borderLeftColor: '#f5b942', background: '#fffdf5', marginTop: 8 }}>
              <p className={styles.subLabel} style={{ color: '#b27720' }}>{i + 1}. {item.title}</p>
              {item.rationale && <p className={styles.llmText}>{item.rationale}</p>}
              {item.action && <p className={styles.llmText}><b>실행 방법</b> — {item.action}</p>}
              {item.success_criteria && <p className={styles.llmText} style={{ color: '#3d9d70' }}><b>확인 기준</b> — {item.success_criteria}</p>}
            </div>
          ))}
        </div>
      )}

      {plan.length > 0 && (
        <div>
          <p className={styles.subLabel} style={{ color: '#3d9d70', fontSize: 15 }}>개인 맞춤형 면접 훈련 계획</p>
          {plan.map((item, i) => (
            <div key={i} className={styles.suggestionBox} style={{ borderLeftColor: '#50eba0', background: '#f0fff8', marginTop: 8 }}>
              <p className={styles.subLabel} style={{ color: '#3d9d70' }}>{item.goal}</p>
              <p className={styles.llmText}>{item.method}</p>
              {item.frequency && <p className={styles.llmText} style={{ color: '#777' }}>주기: {item.frequency}</p>}
              {item.check_criteria && <p className={styles.llmText} style={{ color: '#777' }}>확인 기준: {item.check_criteria}</p>}
            </div>
          ))}
        </div>
      )}
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


export default function ResultsDetail() {
  const navigate    = useNavigate()
  const location    = useLocation()
  const compareData = location.state?.compareData || null
  const [frameModal, setFrameModal] = useState(null)   // { t, label } — 비전 타임라인 클릭 시 프레임 이미지

  const jobId              = compareData?.current?.job_id || null
  const videotype          = compareData?.current?.videotype || null
  const scores             = compareData?.current?.scores || {}
  const previousResult     = compareData?.previous || null
  const scoreDiff          = compareData?.diff || {}
  const [deepReport, setDeepReport] = useState(null)
  const [deepStatus, setDeepStatus] = useState('idle')       // 'idle' | 'loading' | 'ready' | 'error'
  const [scoreHistory, setScoreHistory] = useState([])
  const [historyStatus, setHistoryStatus] = useState('loading')

  function loadDeepReport() {
    if (!jobId || deepStatus === 'loading') return
    setDeepStatus('loading')
    fetch(`/api/deep-report/${jobId}`)
      .then(res => { if (!res.ok) throw new Error(res.status); return res.json() })
      .then(data => { setDeepReport(data); setDeepStatus('ready') })
      .catch(() => setDeepStatus('error'))
  }

  useEffect(() => {
    if (!jobId) return
    setDeepReport(null)
    setDeepStatus('loading')
    let cancelled = false
    fetch(`/api/deep-report/${jobId}`)
      .then(res => { if (!res.ok) throw new Error(res.status); return res.json() })
      .then(data => {
        if (!cancelled) { setDeepReport(data); setDeepStatus('ready') }
      })
      .catch(() => { if (!cancelled) setDeepStatus('error') })
    return () => { cancelled = true }
  }, [jobId])

  useEffect(() => {
    let cancelled = false
    setHistoryStatus('loading')
    getHistory()
      .then(records => {
        if (cancelled) return
        const owner = compareData?.current?.username
        const normalized = records
          .filter(record => !owner || record.username === owner)
          .map(record => ({ ...record, overallScore: getOverallScore(record) }))
          .filter(record => record.overallScore != null && record.timestamp)
          .sort((a, b) => new Date(a.timestamp) - new Date(b.timestamp))
        setScoreHistory(normalized)
        setHistoryStatus('ready')
      })
      .catch(() => {
        if (!cancelled) setHistoryStatus('error')
      })
    return () => { cancelled = true }
  }, [compareData?.current?.username])
  const lang               = compareData?.current?.language_analysis || {}
  const metrics            = lang.metrics || {}
  const raw                = lang.raw_data || {}
  const answers            = compareData?.current?.answers || []
  const displayTranscript  = compareData?.current?.corrected_transcript || raw.transcript || ''

  // ── 비언어 분석 데이터 ───────────────────────────────────────────────────
  const nv              = compareData?.current?.nonverbal_analysis || {}
  const nvStatus        = nv.status || null
  const gazeSummary     = nv.gaze_summary || {}
  const exprSummary     = nv.expression_summary || {}
  const postureSummary  = nv.posture_summary || {}
  const gazeDeductions  = nv.gaze_deductions || []
  const expressionDeductions = nv.expression_deductions || []
  const postureDeductions = nv.posture_deductions || []
  const rawFeatures     = nv.raw_features || {}
  const hasNvData       = nvStatus === 'success' || nvStatus === 'partial'
  const answerEnd       = Math.max(0, ...answers.map(answer => Number(answer.end) || 0))
  const videoDuration   = Math.max(answerEnd, Number(raw.total_duration_sec) || 0)
  const postureReferenceDeductions = postureDeductions.length > 0
    ? postureDeductions
    : videoDuration > 0
      ? [videoDuration / 3, videoDuration * 2 / 3].map(sec => ({ sec, representative: true }))
      : []

  // 자세 부위별 이슈율 중 가장 두드러진 것부터 (구부정/거북목/어깨기울기/고개기울기/몸통회전)
  const POSTURE_PARTS = [
    { key: 'drop',      label: '구부정(머리 처짐)' },
    { key: 'forward',   label: '거북목(고개 전방 돌출)' },
    { key: 'shoulder',  label: '어깨 기울어짐' },
    { key: 'head_tilt', label: '고개 좌우 기울어짐' },
    { key: 'rotation',  label: '몸통 회전' },
  ]
  const postureIssues = POSTURE_PARTS
    .map(p => ({ ...p, rate: rawFeatures[`posture_${p.key}_issue_rate`] }))
    .filter(p => p.rate != null && p.rate > 0)
    .sort((a, b) => b.rate - a.rate)

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

        {/* ── 영상 보기 (실시간/실전연습 세션만) ── */}
        {videotype && jobId && (
          <section className={styles.section}>
            <h3 className={styles.sectionTitle}>
              <span className={styles.sectionDot} style={{ background: '#5BB8F5' }} />
              영상 보기
            </h3>
            <video
              controls
              src={getRealtimeVideoUrl(jobId)}
              style={{ width: '100%', maxHeight: 480, borderRadius: 12, background: '#000' }}
            />
          </section>
        )}

        {/* ── 비전 분석: 표정·자세·시선 (음성 분석과 동일하게 한 섹션으로) ── */}
        <section className={styles.section}>
          <h3 className={styles.sectionTitle}>
            <span className={styles.sectionDot} style={{ background: '#50eba0' }} />
            비전 분석
          </h3>
          {!hasNvData ? (
            <div style={{ padding: '24px 0', textAlign: 'center', color: '#aaa', fontSize: 14,
              border: '1.5px dashed #e0e0e0', borderRadius: 12 }}>
              비전 분석 데이터가 없습니다
            </div>
          ) : (
            <>
              {/* 요약 수치 */}
              <div className={styles.statsRow}>
                {[
                  { label: '표정 안정성 점수', val: scores['표정안정성'] != null ? `${scores['표정안정성']}점` : '—' },
                  { label: '긍정 표정 비율',   val: exprSummary.positive_ratio != null ? `${Math.round(exprSummary.positive_ratio * 100)}%` : '—', color: '#50eba0' },
                  { label: '시선 처리 점수',  val: scores['시선처리'] != null ? `${scores['시선처리']}점` : '—' },
                  { label: '정면 시선 비율',  val: gazeSummary.gaze_ratio != null ? `${Math.round(gazeSummary.gaze_ratio * 100)}%` : '—', color: '#5BB8F5' },
                  { label: '자세 안정성 점수', val: scores['자세안정성'] != null ? `${scores['자세안정성']}점` : '—' },
                  { label: '구부정 횟수',      val: postureSummary.slouch_count != null ? `${postureSummary.slouch_count}회` : '—',
                    color: postureSummary.slouch_count > 5 ? '#f07070' : undefined },
                  { label: '구부정 비율',      val: postureSummary.slouch_ratio != null ? `${Math.round(postureSummary.slouch_ratio * 100)}%` : '—' },
                ].map(s => (
                  <div className={styles.statCard} key={s.label}>
                    <span className={styles.statLabel}>{s.label}</span>
                    <span className={styles.statValue} style={s.color ? { color: s.color } : {}}>{s.val}</span>
                  </div>
                ))}
              </div>

              {/* 표정이 흔들린 구간 — 재확인용 */}
              {expressionDeductions.length > 0 && (
                <div className={styles.deductionList} style={{ marginBottom: 16 }}>
                  <p className={styles.subLabel}>표정이 흔들린 구간 (다시보기)</p>
                  <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
                    {expressionDeductions.slice(0, 8).map((d, i) => (
                      <div
                        key={i}
                        onClick={() => setFrameModal({ group: 'expression', t: d.start, label: `${formatTime(d.start)} — 문제구간 ${i + 1}` })}
                        style={{
                          padding: '6px 12px', borderRadius: 8,
                          background: '#f5f5f5', border: '1px solid #e0e0e0',
                          fontSize: 13, color: '#555', cursor: 'pointer',
                        }}
                      >
                        <span style={{ fontWeight: 700, color: '#50eba0', marginRight: 6 }}>
                          {formatTime(d.start)}
                        </span>
                        문제구간 {i + 1}
                      </div>
                    ))}
                  </div>
                </div>
              )}
              {frameModal?.group === 'expression' && (
                <FrameInline key={`${frameModal.group}-${frameModal.t}`} jobId={jobId} t={frameModal.t} label={frameModal.label} group={frameModal.group} onClose={() => setFrameModal(null)} />
              )}
              <ReferenceComparison jobId={jobId} group="expression" deductions={expressionDeductions} />

              {/* 시선 방향 분포 */}
              {gazeSummary.direction_ratios && (
                <div style={{ marginBottom: 16 }}>
                  <p className={styles.subLabel}>시선 방향 분포</p>
                  <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                    {[
                      { key: 'center', label: '정면', color: '#50eba0' },
                      { key: 'left',   label: '좌',   color: '#5BB8F5' },
                      { key: 'right',  label: '우',   color: '#5BB8F5' },
                      { key: 'up',     label: '위',   color: '#f5b942' },
                      { key: 'down',   label: '아래', color: '#aaa' },
                      { key: 'blink',  label: '깜빡임', color: '#ccc' },
                    ].map(({ key, label, color }) => {
                      const ratio = key === 'center'
                        ? gazeSummary.gaze_ratio
                        : gazeSummary.direction_ratios[key]
                      if (!ratio) return null
                      return (
                        <div key={key} style={{
                          padding: '6px 12px', borderRadius: 8,
                          background: color + '22', border: `1px solid ${color}`,
                          fontSize: 13,
                        }}>
                          <span style={{ color: '#666' }}>{label}</span>
                          <span style={{ color, fontWeight: 700, marginLeft: 6 }}>
                            {Math.round(ratio * 100)}%
                          </span>
                        </div>
                      )
                    })}
                  </div>
                </div>
              )}

              {/* 시선 이탈 구간 */}
              {gazeDeductions.length > 0 && (
                <div className={styles.deductionList} style={{ marginBottom: 16 }}>
                  <p className={styles.subLabel}>시선 이탈 구간</p>
                  <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
                    {gazeDeductions.slice(0, 8).map((d, i) => (
                      <div
                        key={i}
                        onClick={() => setFrameModal({ group: 'gaze', t: d.start, label: `${formatTime(d.start)} — 이탈구간 ${i + 1}` })}
                        style={{
                          padding: '6px 12px', borderRadius: 8,
                          background: '#f5f5f5', border: '1px solid #e0e0e0',
                          fontSize: 13, color: '#555', cursor: 'pointer',
                        }}
                      >
                        <span style={{ fontWeight: 700, color: '#5BB8F5', marginRight: 6 }}>
                          {formatTime(d.start)}
                        </span>
                        이탈구간 {i + 1}
                      </div>
                    ))}
                  </div>
                </div>
              )}
              {frameModal?.group === 'gaze' && (
                <FrameInline key={`${frameModal.group}-${frameModal.t}`} jobId={jobId} t={frameModal.t} label={frameModal.label} group={frameModal.group} onClose={() => setFrameModal(null)} />
              )}
              <ReferenceComparison jobId={jobId} group="gaze" deductions={gazeDeductions} />

              {/* 구부정 구간 */}
              {postureDeductions.length > 0 && (
                <div className={styles.deductionList} style={{ marginBottom: 16 }}>
                  <p className={styles.subLabel}>구부정 감지 구간</p>
                  <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
                    {postureDeductions.slice(0, 8).map((d, i) => (
                      <div
                        key={i}
                        onClick={() => setFrameModal({ group: 'posture', t: d.sec, label: `${formatTime(d.sec)} — 구부정 (신뢰도 ${Math.round(d.confidence * 100)}%)` })}
                        style={{
                          padding: '6px 12px', borderRadius: 8,
                          background: '#fff5f5', border: '1px solid #f07070',
                          fontSize: 13, color: '#555', cursor: 'pointer',
                        }}
                      >
                        <span style={{ fontWeight: 700, color: '#f07070', marginRight: 6 }}>
                          {formatTime(d.sec)}
                        </span>
                        구부정 (신뢰도 {Math.round(d.confidence * 100)}%)
                      </div>
                    ))}
                  </div>
                </div>
              )}
              {frameModal?.group === 'posture' && (
                <FrameInline key={`${frameModal.group}-${frameModal.t}`} jobId={jobId} t={frameModal.t} label={frameModal.label} group={frameModal.group} onClose={() => setFrameModal(null)} />
              )}
              <ReferenceComparison jobId={jobId} group="posture" deductions={postureReferenceDeductions} />

              {/* 감지된 시선·표정·자세 특징만 근거로 한 분석 */}
              {deepStatus === 'ready' && deepReport
                ? <VisionDeepAnalysis report={deepReport} />
                : <div style={{ margin: '18px 0' }}><ReportState status={deepStatus} onRetry={loadDeepReport} /></div>
              }

              {/* 피드백 */}
              <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
                {exprSummary.feedback && (
                  <div className={styles.suggestionBox} style={{ borderLeftColor: '#50eba0', background: '#f0fff8' }}>
                    <p className={styles.subLabel} style={{ color: '#50eba0' }}>표정 피드백</p>
                    <p className={styles.llmText}>{exprSummary.feedback}</p>
                  </div>
                )}
                {gazeSummary.feedback && (
                  <div className={styles.suggestionBox} style={{ borderLeftColor: '#5BB8F5', background: '#f0f7ff' }}>
                    <p className={styles.subLabel} style={{ color: '#5BB8F5' }}>시선 피드백</p>
                    <p className={styles.llmText}>{gazeSummary.feedback}</p>
                  </div>
                )}
                {postureSummary.feedback && (
                  <div className={styles.suggestionBox} style={{ borderLeftColor: '#5BB8F5', background: '#f0f7ff' }}>
                    <p className={styles.subLabel} style={{ color: '#5BB8F5' }}>자세 피드백</p>
                    <p className={styles.llmText}>{postureSummary.feedback}</p>
                    {postureIssues.length > 0 && (
                      <div style={{ display: 'flex', flexDirection: 'column', gap: 6, marginTop: 10 }}>
                        {postureIssues.slice(0, 3).map(p => (
                          <div key={p.key} style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                            <span style={{ width: 140, fontSize: 12, color: '#666', flexShrink: 0 }}>{p.label}</span>
                            <div style={{ flex: 1, height: 8, background: '#e6f0fb', borderRadius: 4 }}>
                              <div style={{ width: `${Math.round(p.rate * 100)}%`, height: '100%', background: '#5BB8F5', borderRadius: 4 }} />
                            </div>
                            <span style={{ width: 36, fontSize: 12, color: '#888', textAlign: 'right' }}>
                              {Math.round(p.rate * 100)}%
                            </span>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                )}
              </div>
            </>
          )}
        </section>

        {/* ── 음성 분석 ── */}
        <section className={styles.section}>
          <h3 className={styles.sectionTitle}>
            <span className={styles.sectionDot} style={{ background: '#50eba0' }} />
            음성 분석
          </h3>

          {!hasLangData ? (
            <div style={{ padding: '24px 0', textAlign: 'center', color: '#aaa', fontSize: 14 }}>
              음성 분석 데이터를 불러올 수 없습니다.
            </div>
          ) : (
            <>
              {/* 요약 수치 */}
              <div className={styles.statsRow}>
                {[
                  { label: '발화 속도 점수', val: `${scores['발화속도'] ?? '—'}점` },
                  { label: '음성 명확성 점수', val: `${scores['음성명확성'] ?? '—'}점` },
                  { label: '유창성·침묵 점수', val: `${scores['유창성침묵'] ?? '—'}점` },
                  { label: '습관어 점수',    val: `${scores['습관어'] ?? '—'}점` },
                  { label: '속도 평가',      val: speechRate.label || '—',   color: '#50eba0' },
                  { label: '분당 음절 수',   val: speechRate.spm != null ? `${Math.round(speechRate.spm)} spm` : '—' },
                  { label: '습관어 횟수',    val: `${fillers.count}회` },
                  { label: '더듬음 횟수',    val: `${stutters.count}회` },
                  { label: '긴 침묵 횟수',   val: `${pauses.count}회` },
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

              {/* 감지된 발화 특징만 근거로 한 분석 */}
              {deepStatus === 'ready' && deepReport
                ? <VoiceDeepAnalysis report={deepReport} />
                : <div style={{ margin: '18px 0' }}><ReportState status={deepStatus} onRetry={loadDeepReport} /></div>
              }

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

        {/* ── 음성·비전 특징을 합친 최종 면접 태도 리포트 ── */}
        <section className={styles.section}>
          <h3 className={styles.sectionTitle}>
            <span className={styles.sectionDot} style={{ background: '#5BB8F5' }} />
            종합 리포트
          </h3>
          {deepStatus === 'ready' && deepReport
            ? <OverallReportView report={deepReport} />
            : <ReportState status={deepStatus} onRetry={loadDeepReport} />
          }
        </section>

        {/* ── 이전 기록과의 변화 비교 ── */}
        <section className={styles.section}>
          <h3 className={styles.sectionTitle}>
            <span className={styles.sectionDot} style={{ background: '#50eba0' }} />
            이전 면접과 비교
          </h3>
          <p className={styles.llmText} style={{ color: '#777', margin: '0 0 14px' }}>
            파란 막대는 이전 면접, 빨간 막대는 이번 면접입니다. 항목별 막대 높이를 비교해 면접 태도의 변화를 확인할 수 있습니다.
          </p>
          <InterviewComparison
            current={compareData?.current}
            previous={previousResult}
            diff={scoreDiff}
          />
        </section>

        {/* ── 시간별 종합 점수 추이 ── */}
        <section className={styles.section}>
          <h3 className={styles.sectionTitle}>
            <span className={styles.sectionDot} style={{ background: '#5BB8F5' }} />
            시간별 종합 점수 추이
          </h3>
          <p className={styles.llmText} style={{ color: '#777', margin: '0 0 14px' }}>
            지금까지 완료한 면접의 종합 점수를 시간순으로 보여줍니다.
          </p>
          {historyStatus === 'loading' && (
            <p className={styles.llmText} style={{ color: '#888' }}>점수 기록을 불러오는 중입니다...</p>
          )}
          {historyStatus === 'error' && (
            <p className={styles.llmText} style={{ color: '#f07070' }}>점수 기록을 불러오지 못했습니다.</p>
          )}
          {historyStatus === 'ready' && scoreHistory.length === 0 && (
            <p className={styles.llmText} style={{ color: '#888' }}>표시할 점수 기록이 없습니다.</p>
          )}
          {historyStatus === 'ready' && scoreHistory.length > 0 && (
            <ScoreTrendChart records={scoreHistory} />
          )}
        </section>
      </main>
    </div>
  )
}
