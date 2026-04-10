import { useNavigate } from 'react-router-dom'
import RadarChart from '../components/RadarChart'
import styles from '../styles/ResultsDetail.module.css'

// ResultsDetail의 좌측 패널용 인라인 로고 (position:fixed 불가 — 패널 내 배치)
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

// ── 목업 데이터 (백엔드 연결 시 교체) ──────────────────────────────
const MOCK_SCORES = {
  표정안정성: 78, 표정다양성: 62,
  자세안정성: 85, 시선처리: 70,
  발화속도: 88,   말하기명확성: 74,
}

const SCORE_LABELS = [
  { key: '표정안정성', label: '표정 안정성', color: '#50eba0' },
  { key: '표정다양성', label: '표정 다양성', color: '#5BB8F5' },
  { key: '자세안정성', label: '자세 안정성', color: '#50eba0' },
  { key: '시선처리',   label: '시선 처리',   color: '#5BB8F5' },
  { key: '발화속도',   label: '발화 속도',   color: '#50eba0' },
  { key: '말하기명확성', label: '말하기 명확성', color: '#5BB8F5' },
]

const MOCK = {
  face: {
    stability: 78, diversity: 62, eyeContact: 70,
    dominantEmotion: '긴장',
    emotionDist: [
      { label: '중립',   value: 45 },
      { label: '긴장',   value: 30 },
      { label: '자신감', value: 15 },
      { label: '기타',   value: 10 },
    ],
    deductions: [
      { timestamp: '00:32', thumbnailUrl: null, desc: '눈을 과도하게 아래로 내려깔았습니다.' },
      { timestamp: '01:14', thumbnailUrl: null, desc: '긴장된 표정이 지속되었습니다.' },
    ],
    llmSuggestion: '면접 중 시선을 카메라 렌즈에 고정하고, 입꼬리를 자연스럽게 올려 자신감 있는 표정을 유지해보세요. 거울 앞에서 반복 연습을 권장합니다.',
    correctionImageUrl: null,
  },
  posture: {
    stabilityScore: 85,
    deductions: [
      { timestamp: '00:47', thumbnailUrl: null, desc: '어깨가 앞으로 굽어졌습니다.' },
      { timestamp: '02:03', thumbnailUrl: null, desc: '상체가 좌측으로 기울었습니다.' },
    ],
    llmSuggestion: '등을 곧게 펴고 어깨를 뒤로 당기는 자세를 유지하세요. 의자 등받이에 허리를 붙이면 장시간 올바른 자세를 유지하는 데 도움이 됩니다.',
    correctionImageUrl: null,
  },
  speech: {
    rate: 88, rateLabel: '적절', stutterCount: 2,
    fillerWords: [
      { word: '저', count: 12 }, { word: '그', count: 8 },
      { word: '음', count: 5 },  { word: '좀', count: 3 },
    ],
    deductions: [
      { timestamp: '00:58', desc: '습관어 "저" 4회 연속 사용' },
      { timestamp: '01:45', desc: '더듬음 발생 - "그그그 그래서"' },
    ],
    llmSuggestion: '말하기 전 짧은 침묵(1~2초)을 두는 연습을 해보세요. 습관어를 인식하고 줄이려면 본인의 면접 영상을 반복해서 시청하며 모니터링하는 것이 효과적입니다.',
  },
}
// ─────────────────────────────────────────────────────────────────────

function getGrade(score) {
  if (score >= 90) return { text: '매우 우수', color: '#50eba0' }
  if (score >= 75) return { text: '우수',     color: '#5BB8F5' }
  if (score >= 60) return { text: '보통',     color: '#f5b942' }
  return               { text: '개선 필요', color: '#f07070' }
}

function TimestampClip({ timestamp, thumbnailUrl, desc, isAudio }) {
  return (
    <div className={styles.clipItem}>
      <span className={styles.timestamp}>{timestamp}</span>
      {!isAudio && (
        <div className={styles.thumbnail}>
          {thumbnailUrl
            ? <img src={thumbnailUrl} alt="클립" />
            : <div className={styles.thumbnailPlaceholder}>
                <svg viewBox="0 0 32 32" fill="none">
                  <rect x="2" y="6" width="28" height="20" rx="3" stroke="#ccc" strokeWidth="1.5"/>
                  <circle cx="11" cy="14" r="3" stroke="#ccc" strokeWidth="1.5"/>
                  <path d="M2 22l7-6 5 5 4-4 12 9" stroke="#ccc" strokeWidth="1.5"/>
                </svg>
              </div>
          }
        </div>
      )}
      {isAudio && (
        <div className={styles.audioClip}>
          <svg viewBox="0 0 32 16" fill="none">
            <rect x="0"  y="6" width="2" height="4"  rx="1" fill="#50eba0"/>
            <rect x="4"  y="3" width="2" height="10" rx="1" fill="#50eba0"/>
            <rect x="8"  y="1" width="2" height="14" rx="1" fill="#5BB8F5"/>
            <rect x="12" y="4" width="2" height="8"  rx="1" fill="#50eba0"/>
            <rect x="16" y="2" width="2" height="12" rx="1" fill="#5BB8F5"/>
            <rect x="20" y="5" width="2" height="6"  rx="1" fill="#50eba0"/>
            <rect x="24" y="3" width="2" height="10" rx="1" fill="#5BB8F5"/>
            <rect x="28" y="6" width="2" height="4"  rx="1" fill="#50eba0"/>
          </svg>
          <span className={styles.audioLabel}>음성 클립</span>
        </div>
      )}
      <p className={styles.clipDesc}>{desc}</p>
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
  const navigate = useNavigate()
  const { face, posture, speech } = MOCK
  const scores  = Object.values(MOCK_SCORES)
  const avg     = Math.round(scores.reduce((a, b) => a + b, 0) / scores.length)
  const avgGrade = getGrade(avg)

  return (
    <div className={styles.pageLayout}>

      {/* ════════════════ 좌측 패널: 레이더 차트 (고정) ════════════════ */}
      <aside className={styles.leftPanel}>
        <div className={styles.leftInner}>
          <PanelLogo />
          <h2 className={styles.leftTitle}>분석 결과</h2>

          <div className={styles.avgBadge}>
            <span className={styles.avgScore}>{avg}점</span>
            <span className={styles.avgGrade} style={{ color: avgGrade.color }}>{avgGrade.text}</span>
          </div>

          <div className={styles.chartWrap}>
            <RadarChart scores={scores} />
          </div>

          {/* 항목별 점수 */}
          <div className={styles.scoreList}>
            {SCORE_LABELS.map(({ key, label, color }) => {
              const score = MOCK_SCORES[key]
              const grade = getGrade(score)
              return (
                <div className={styles.scoreRow} key={key}>
                  <span className={styles.scoreLabel}>{label}</span>
                  <div className={styles.scoreTrack}>
                    <div className={styles.scoreFill} style={{ width: `${score}%`, background: color }} />
                  </div>
                  <span className={styles.scoreNum}>{score}</span>
                  <span className={styles.scoreGrade} style={{ color: grade.color }}>{grade.text}</span>
                </div>
              )
            })}
          </div>

          {/* 버튼 */}
          <div className={`${styles.leftActions} ${styles.printHide}`}>
            <button className={styles.pdfBtn} onClick={() => window.print()}>
              <svg viewBox="0 0 20 20" fill="none">
                <path d="M6 2h8l4 4v12H2V2h4z" stroke="currentColor" strokeWidth="1.5"/>
                <path d="M6 2v4h8V2" stroke="currentColor" strokeWidth="1.5"/>
                <path d="M6 12h8M6 15h5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/>
              </svg>
              PDF로 저장
            </button>
            <button className={styles.homeBtn} onClick={() => navigate('/')}>
              처음으로
            </button>
          </div>
        </div>
      </aside>

      {/* ════════════════ 우측 패널: 상세 분석 (스크롤) ════════════════ */}
      <main className={styles.rightPanel}>
        <h2 className={styles.rightTitle}>상세 분석 결과</h2>

        {/* ── 표정 분석 ── */}
        <section className={styles.section}>
          <h3 className={styles.sectionTitle}>
            <span className={styles.sectionDot} style={{ background: '#50eba0' }} />
            표정 분석
          </h3>

          <div className={styles.statsRow}>
            {[
              { label: '표정 안정성', val: `${face.stability}점` },
              { label: '표정 다양성', val: `${face.diversity}점` },
              { label: '시선 처리',   val: `${face.eyeContact}점` },
              { label: '주요 감정',   val: face.dominantEmotion },
            ].map(s => (
              <div className={styles.statCard} key={s.label}>
                <span className={styles.statLabel}>{s.label}</span>
                <span className={styles.statValue}>{s.val}</span>
              </div>
            ))}
          </div>

          <div className={styles.emotionBars}>
            <p className={styles.subLabel}>감정 분포</p>
            {face.emotionDist.map(e => (
              <div className={styles.emotionRow} key={e.label}>
                <span className={styles.emotionLabel}>{e.label}</span>
                <div className={styles.emotionTrack}>
                  <div className={styles.emotionFill} style={{ width: `${e.value}%` }} />
                </div>
                <span className={styles.emotionPct}>{e.value}%</span>
              </div>
            ))}
          </div>

          <div className={styles.deductionList}>
            <p className={styles.subLabel}>감점 발생 구간</p>
            <div className={styles.clips}>
              {face.deductions.map((d, i) => (
                <TimestampClip key={i} timestamp={d.timestamp} thumbnailUrl={d.thumbnailUrl} desc={d.desc} />
              ))}
            </div>
          </div>

          <div className={styles.suggestionBox}>
            <p className={styles.subLabel}>교정 제안</p>
            <CorrectionImageSlot url={face.correctionImageUrl} />
            <p className={styles.llmText}>{face.llmSuggestion}</p>
          </div>
        </section>

        {/* ── 자세 분석 ── */}
        <section className={styles.section}>
          <h3 className={styles.sectionTitle}>
            <span className={styles.sectionDot} style={{ background: '#5BB8F5' }} />
            자세 분석
          </h3>

          <div className={styles.statsRow}>
            <div className={styles.statCard}>
              <span className={styles.statLabel}>자세 안정성</span>
              <span className={styles.statValue}>{posture.stabilityScore}점</span>
            </div>
          </div>

          <div className={styles.deductionList}>
            <p className={styles.subLabel}>감점 발생 구간</p>
            <div className={styles.clips}>
              {posture.deductions.map((d, i) => (
                <TimestampClip key={i} timestamp={d.timestamp} thumbnailUrl={d.thumbnailUrl} desc={d.desc} />
              ))}
            </div>
          </div>

          <div className={styles.suggestionBox}>
            <p className={styles.subLabel}>교정 제안</p>
            <CorrectionImageSlot url={posture.correctionImageUrl} />
            <p className={styles.llmText}>{posture.llmSuggestion}</p>
          </div>
        </section>

        {/* ── 말하기 분석 ── */}
        <section className={styles.section}>
          <h3 className={styles.sectionTitle}>
            <span className={styles.sectionDot} style={{ background: '#50eba0' }} />
            말하기 분석
          </h3>

          <div className={styles.statsRow}>
            {[
              { label: '발화 속도',   val: `${speech.rate}점` },
              { label: '속도 평가',   val: speech.rateLabel, color: '#50eba0' },
              { label: '더듬음 횟수', val: `${speech.stutterCount}회` },
            ].map(s => (
              <div className={styles.statCard} key={s.label}>
                <span className={styles.statLabel}>{s.label}</span>
                <span className={styles.statValue} style={s.color ? { color: s.color } : {}}>{s.val}</span>
              </div>
            ))}
          </div>

          <div className={styles.fillerWords}>
            <p className={styles.subLabel}>습관어 빈도</p>
            <div className={styles.fillerGrid}>
              {speech.fillerWords.map(f => (
                <div className={styles.fillerItem} key={f.word}>
                  <span className={styles.fillerWord}>"{f.word}"</span>
                  <span className={styles.fillerCount}>{f.count}회</span>
                </div>
              ))}
            </div>
          </div>

          <div className={styles.deductionList}>
            <p className={styles.subLabel}>감점 발생 구간</p>
            <div className={styles.clips}>
              {speech.deductions.map((d, i) => (
                <TimestampClip key={i} timestamp={d.timestamp} desc={d.desc} isAudio />
              ))}
            </div>
          </div>

          <div className={styles.suggestionBox}>
            <p className={styles.subLabel}>교정 제안</p>
            <p className={styles.llmText}>{speech.llmSuggestion}</p>
          </div>
        </section>
      </main>
    </div>
  )
}
