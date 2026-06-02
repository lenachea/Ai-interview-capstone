import { useNavigate, useLocation } from 'react-router-dom'
import RadarChart from '../components/RadarChart'
import AppLogo from '../components/AppLogo'
import styles from '../styles/ResultsOverview.module.css'

// 레이더 차트 항목 순서 (RadarChart labels와 동일하게 유지)
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

function DiffBadge({ diff }) {
  if (diff == null) return null
  const sign  = diff > 0 ? '+' : ''
  const color = diff > 0 ? '#50eba0' : diff < 0 ? '#f07070' : '#aaa'
  return (
    <span style={{
      fontSize: 11, fontWeight: 700, color,
      marginLeft: 4, padding: '1px 5px',
      borderRadius: 6, background: color + '22',
    }}>
      {sign}{diff}
    </span>
  )
}

export default function ResultsOverview() {
  const navigate    = useNavigate()
  const location    = useLocation()
  const compareData = location.state?.compareData || null
  const errorMsg    = location.state?.error       || null

  const scores = compareData?.current?.scores || null
  const diff   = compareData?.diff            || {}
  const hasPrev = compareData?.previous != null

  // 레이더 차트용 숫자 배열 (null → 0)
  const radarValues = SCORE_LABELS.map(({ key }) => scores?.[key] ?? 0)

  // 총점: 유효한 점수만 평균
  const validScores = SCORE_LABELS.map(({ key }) => scores?.[key]).filter(v => v != null)
  const avg = validScores.length > 0
    ? Math.round(validScores.reduce((a, b) => a + b, 0) / validScores.length)
    : null
  const avgGrade = getGrade(avg)

  if (errorMsg) {
    return (
      <div className={styles.container}>
        <AppLogo />
        <div className={styles.gradientMint} />
        <div className={styles.gradientBlue} />
        <div className={styles.content}>
          <h2 className={styles.title}>분석 실패</h2>
          <p style={{ color: '#f07070', marginTop: 12 }}>{errorMsg}</p>
          <div className={styles.actions}>
            <button className={styles.homeBtn} onClick={() => navigate('/')}>처음으로</button>
          </div>
        </div>
      </div>
    )
  }

  return (
    <div className={styles.container}>
      <AppLogo />
      <div className={styles.gradientMint} />
      <div className={styles.gradientBlue} />

      <div className={styles.content}>
        <div className={styles.header}>
          <h2 className={styles.title}>분석 결과</h2>
          <div className={styles.avgBadge}>
            <span className={styles.avgScore}>
              {avg != null ? `${avg}점` : '집계 중'}
            </span>
            <span className={styles.avgGrade} style={{ color: avgGrade.color }}>
              {avgGrade.text}
            </span>
            {hasPrev && diff['총점'] != null && <DiffBadge diff={diff['총점']} />}
          </div>
        </div>

        {/* 레이더 차트 */}
        <div className={styles.chartWrap}>
          <RadarChart scores={radarValues} />
        </div>

        {/* 항목별 점수 요약 */}
        <div className={styles.scoreGrid}>
          {SCORE_LABELS.map(({ key, label, color }) => {
            const score = scores?.[key] ?? null
            const grade = getGrade(score)
            return (
              <div className={styles.scoreItem} key={key}>
                <span className={styles.scoreLabel}>{label}</span>
                <div className={styles.scoreBar}>
                  {score != null ? (
                    <div
                      className={styles.scoreBarFill}
                      style={{ width: `${score}%`, background: color }}
                    />
                  ) : (
                    <div
                      className={styles.scoreBarFill}
                      style={{ width: '100%', background: '#eee' }}
                    />
                  )}
                </div>
                <span className={styles.scoreValue}>
                  {score != null ? score : '—'}
                </span>
                <span className={styles.scoreGrade} style={{ color: grade.color }}>
                  {grade.text}
                </span>
                {score != null && <DiffBadge diff={diff[key]} />}
              </div>
            )
          })}
        </div>

        {!hasPrev && scores != null && (
          <p style={{ textAlign: 'center', color: '#aaa', fontSize: 12, marginTop: 4 }}>
            첫 분석 결과입니다. 다음 분석 시 비교 점수가 표시됩니다.
          </p>
        )}

        <div className={styles.actions}>
          <button
            className={styles.detailBtn}
            onClick={() => navigate('/results/detail', { state: location.state })}
          >
            자세히 보기
          </button>
          <button className={styles.homeBtn} onClick={() => navigate('/')}>
            처음으로
          </button>
        </div>
      </div>
    </div>
  )
}
