import type { ChartData, ChartOptions } from "chart.js";
import { Bar } from "react-chartjs-2";
import { COLORS, MONTHS, num } from "../format";
import type { Analysis } from "../types";

const options: ChartOptions<"bar"> = {
  interaction: { mode: "index", intersect: false },
  scales: {
    x: { grid: { display: false } },
    y: { beginAtZero: true, title: { display: true, text: "heatwave days per year" }, grid: { color: COLORS.grid } },
  },
  plugins: {
    tooltip: {
      callbacks: { label: (item) => `${item.dataset.label}: ${num(item.raw as number, 2)} days per year` },
    },
  },
};

export default function SeasonChart({ analysis }: { analysis: Analysis }) {
  const { early, late } = analysis.monthly;
  const data: ChartData<"bar"> = {
    labels: MONTHS,
    datasets: [
      { label: `${early.from}–${early.to}`, data: early.days, backgroundColor: COLORS.neutral, borderRadius: 3 },
      { label: `${late.from}–${late.to}`, data: late.days, backgroundColor: COLORS.heat, borderRadius: 3 },
    ],
  };
  return (
    <section className="card">
      <h2>When in the year</h2>
      <p className="card-sub">Average heatwave days per month, first half of the period against the second</p>
      <div className="chart chart-short">
        <Bar data={data} options={options} />
      </div>
    </section>
  );
}
