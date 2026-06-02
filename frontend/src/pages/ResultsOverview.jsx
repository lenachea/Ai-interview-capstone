import { useNavigate } from 'react-router-dom'
import RadarChart from '../components/RadarChart'
import AppLogo from '../components/AppLogo'
import styles from '../styles/ResultsOverview.module.css'

// 목업 데이터 (백엔드 연결 시 props 또는 context로 교체)
const MOCK_SCORES = {
  표정안정성: 78,
  표정다양성: 62,
  자세안정성: 85,
  시선처리: 70,
  발화속도: 88,
  말하기명확성: 74,
}

const SCORE_LABELS = [
  { key: '표정안정성', label: '표정 안정성', color: '#50eba0' },
  { key: '표정다양성', label: '표정 다양성', color: '#5BB8F5' },
  { key: '자세안정성', label: '자세 안정성', color: '#50eba0' },
  { key: '시선처리', label: '시선 처리', color: '#5BB8F5' },
  { key: '발화속도', label: '발화 속도', color: '#50eba0' },
  { key: '말하기명확성', label: '말하기 명확성', color: '#5BB8F5' },
]

function getGrade(score) {
  if (score >= 90) return { text: '매우 우수', color: '#50eba0' }
  if (score >= 75) return { text: '우수', color: '#5BB8F5' }
  if (score >= 60) return { text: '보통', color: '#f5b942' }
  return { text: '개선 필요', color: '#f07070' }
}

export default function ResultsOverview() {
  const navigate = useNavigate()
  const scores = Object.values(MOCK_SCORES)
  const avg = Math.round(scores.reduce((a, b) => a + b, 0) / scores.length)
  const avgGrade = getGrade(avg)

  return (
    <div className={styles.container}>
      <AppLogo />
      <div className={styles.stripesMint} />
      <div className={styles.stripesBlue} />

      <div className={styles.content}>
        <div className={styles.header}>
          <h2 className={styles.title}>분석 결과</h2>
          <div className={styles.avgBadge}>
            <span className={styles.avgScore}>{avg}점</span>
            <span className={styles.avgGrade} style={{ color: avgGrade.color }}>{avgGrade.text}</span>
          </div>
        </div>

        {/* 레이더 차트 */}
        <div className={styles.chartWrap}>
          <RadarChart scores={scores} />
        </div>

        {/* 항목별 점수 요약 */}
        <div className={styles.scoreGrid}>
          {SCORE_LABELS.map(({ key, label, color }) => {
            const score = MOCK_SCORES[key]
            const grade = getGrade(score)
            return (
              <div className={styles.scoreItem} key={key}>
                <span className={styles.scoreLabel}>{label}</span>
                <div className={styles.scoreBar}>
                  <div
                    className={styles.scoreBarFill}
                    style={{ width: `${score}%`, background: color }}
                  />
                </div>
                <span className={styles.scoreValue}>{score}</span>
                <span className={styles.scoreGrade} style={{ color: grade.color }}>{grade.text}</span>
              </div>
            )
          })}
        </div>

        <div className={styles.actions}>
          <button
            className={styles.detailBtn}
            onClick={() => navigate('/results/detail')}
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
