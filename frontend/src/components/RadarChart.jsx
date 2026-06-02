import {
  Chart as ChartJS,
  RadialLinearScale,
  PointElement,
  LineElement,
  Filler,
  Tooltip,
  Legend,
} from 'chart.js'
import { Radar } from 'react-chartjs-2'

ChartJS.register(RadialLinearScale, PointElement, LineElement, Filler, Tooltip, Legend)

export default function RadarChart({ scores }) {
  const labels = ['표정 안정성', '표정 다양성', '자세 안정성', '시선 처리', '발화 속도', '말하기 명확성']

  const data = {
    labels,
    datasets: [
      {
        label: '분석 점수',
        data: scores,
        backgroundColor: 'rgba(80, 235, 160, 0.2)',
        borderColor: '#50eba0',
        borderWidth: 2.5,
        pointBackgroundColor: '#50eba0',
        pointBorderColor: '#fff',
        pointBorderWidth: 2,
        pointRadius: 5,
        pointHoverRadius: 7,
      },
    ],
  }

  const options = {
    responsive: true,
    maintainAspectRatio: true,
    scales: {
      r: {
        min: 0,
        max: 100,
        ticks: {
          stepSize: 20,
          color: '#aaa',
          font: { size: 11, family: "'Noto Sans KR', sans-serif" },
          backdropColor: 'transparent',
        },
        grid: { color: 'rgba(0,0,0,0.08)' },
        angleLines: { color: 'rgba(0,0,0,0.08)' },
        pointLabels: {
          font: { size: 13, family: "'Noto Sans KR', sans-serif", weight: '500' },
          color: '#444',
        },
      },
    },
    plugins: {
      legend: { display: false },
      tooltip: {
        callbacks: {
          label: ctx => ` ${ctx.raw}점`,
        },
      },
    },
  }

  return <Radar data={data} options={options} />
}
