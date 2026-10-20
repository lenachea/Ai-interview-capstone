import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  BarElement,
  Tooltip,
  Legend,
} from 'chart.js'
import { Bar } from 'react-chartjs-2'

ChartJS.register(CategoryScale, LinearScale, BarElement, Tooltip, Legend)

const valueLabelsPlugin = {
  id: 'comparisonValueLabels',
  afterDatasetsDraw(chart) {
    const { ctx } = chart
    ctx.save()
    ctx.textAlign = 'center'
    ctx.font = "700 11px 'Noto Sans KR', sans-serif"
    chart.data.datasets.forEach((dataset, datasetIndex) => {
      const meta = chart.getDatasetMeta(datasetIndex)
      meta.data.forEach((bar, index) => {
        const value = dataset.data[index]
        if (value == null) return
        ctx.fillStyle = dataset.borderColor
        ctx.fillText(`${value}`, bar.x, bar.y - 7)
      })
    })
    ctx.restore()
  },
}

export default function ComparisonChart({ labels, currentScores, previousScores }) {
  const data = {
    labels,
    datasets: [
      {
        label: '이전 면접',
        data: previousScores,
        backgroundColor: 'rgba(64, 87, 214, 0.78)',
        borderColor: '#4057d6',
        borderWidth: 1,
        borderRadius: 6,
        borderSkipped: false,
        maxBarThickness: 38,
      },
      {
        label: '이번 면접',
        data: currentScores,
        backgroundColor: 'rgba(255, 112, 112, 0.82)',
        borderColor: '#ff7070',
        borderWidth: 1,
        borderRadius: 6,
        borderSkipped: false,
        maxBarThickness: 38,
      },
    ],
  }

  const options = {
    responsive: true,
    maintainAspectRatio: false,
    scales: {
      x: {
        grid: { display: false },
        ticks: { color: '#555', font: { size: 11, weight: '500' } },
      },
      y: {
        min: 0,
        max: 105,
        grid: { color: 'rgba(0,0,0,0.06)' },
        ticks: { stepSize: 20, color: '#999' },
      },
    },
    plugins: {
      legend: {
        position: 'bottom',
        labels: { usePointStyle: true, pointStyle: 'rectRounded', padding: 22, font: { size: 13 } },
      },
      tooltip: {
        callbacks: { label: context => ` ${context.dataset.label}: ${context.raw}점` },
      },
    },
  }

  return (
    <div style={{ height: 330, width: '100%' }}>
      <Bar data={data} options={options} plugins={[valueLabelsPlugin]} />
    </div>
  )
}
