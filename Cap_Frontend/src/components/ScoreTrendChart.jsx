import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  Filler,
  Tooltip,
  Legend,
} from 'chart.js'
import { Line } from 'react-chartjs-2'

ChartJS.register(CategoryScale, LinearScale, PointElement, LineElement, Filler, Tooltip, Legend)

function formatAxisTime(timestamp) {
  const date = new Date(timestamp)
  if (Number.isNaN(date.getTime())) return timestamp || '-'
  return date.toLocaleString('ko-KR', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  })
}

function formatFullTime(timestamp) {
  const date = new Date(timestamp)
  if (Number.isNaN(date.getTime())) return timestamp || '-'
  return date.toLocaleString('ko-KR', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  })
}

export default function ScoreTrendChart({ records }) {
  const data = {
    labels: records.map(record => formatAxisTime(record.timestamp)),
    datasets: [
      {
        label: '종합 점수',
        data: records.map(record => record.overallScore),
        borderColor: '#5BB8F5',
        backgroundColor: 'rgba(91, 184, 245, 0.14)',
        pointBackgroundColor: '#50eba0',
        pointBorderColor: '#fff',
        pointBorderWidth: 2,
        pointRadius: 5,
        pointHoverRadius: 7,
        borderWidth: 3,
        tension: 0.28,
        fill: true,
      },
    ],
  }

  const options = {
    responsive: true,
    maintainAspectRatio: false,
    interaction: { mode: 'index', intersect: false },
    scales: {
      x: {
        grid: { display: false },
        ticks: { color: '#666', maxRotation: 35, minRotation: 0, font: { size: 11 } },
      },
      y: {
        min: 0,
        max: 100,
        grid: { color: 'rgba(0,0,0,0.06)' },
        ticks: { stepSize: 20, color: '#999', callback: value => `${value}점` },
      },
    },
    plugins: {
      legend: { display: false },
      tooltip: {
        callbacks: {
          title: contexts => formatFullTime(records[contexts[0]?.dataIndex]?.timestamp),
          label: context => ` 종합 점수: ${context.raw}점`,
        },
      },
    },
  }

  return (
    <div style={{ height: 320, width: '100%' }}>
      <Line data={data} options={options} />
    </div>
  )
}
