import type { ChartData, ChartOptions } from "chart.js";
import { useMemo } from "react";
import { Chart } from "react-chartjs-2";
import { COLORS, METRICS, num, pValue, signed } from "../format";
import type { Analysis, MetricKey } from "../types";

interface Props {
  analysis: Analysis;
  metric: MetricKey;
  selectedYear: number | null;
  onMetric: (metric: MetricKey) => void;
  onYear: (year: number) => void;
}

const VERDICT = {
  increasing: "Increasing",
  decreasing: "Decreasing",
  no_significant_trend: "No significant trend",
};

export default function TrendChart({ analysis, metric, selectedYear, onMetric, onYear }: Props) {
  const meta = METRICS[metric];
  const trend = analysis.trends[metric];
  const years = analysis.annual.map((row) => row.year);

  const data = useMemo<ChartData>(() => {
    const yearly = analysis.annual.map((row) => row[metric]);
    const fitted =
      trend.status === "ok" ? years.map((y) => trend.ols.intercept + trend.ols.slope * y) : [];
    const barColor = analysis.annual.map((row) =>
      !row.complete ? COLORS.sand : row.year === selectedYear ? COLORS.burgundy : COLORS.burgundySoft,
    );
    return {
      labels: years,
      datasets: [
        {
          type: "line",
          label: "5-year mean",
          data: analysis.rolling[metric],
          borderColor: COLORS.navy,
          backgroundColor: COLORS.navy,
          borderWidth: 2.5,
          pointRadius: 0,
          tension: 0.25,
          spanGaps: true,
        },
        {
          type: "line",
          label: "Linear trend",
          data: fitted,
          borderColor: COLORS.ink,
          backgroundColor: COLORS.ink,
          borderWidth: 1.5,
          borderDash: [6, 4],
          pointRadius: 0,
        },
        meta.bars
          ? {
              type: "bar",
              label: "Yearly value",
              data: yearly,
              backgroundColor: barColor,
              hoverBackgroundColor: COLORS.burgundy,
              categoryPercentage: 0.82,
              barPercentage: 0.9,
            }
          : {
              type: "line",
              label: "Yearly value",
              data: yearly,
              borderColor: COLORS.burgundySoft,
              backgroundColor: barColor,
              pointBorderColor: COLORS.burgundy,
              borderWidth: 1.5,
              pointRadius: 3.5,
              pointHoverRadius: 6,
              spanGaps: false,
            },
      ],
    } as ChartData;
  }, [analysis, metric, selectedYear]);

  const options = useMemo<ChartOptions>(
    () => ({
      interaction: { mode: "index", intersect: false },
      onClick: (_event, elements) => {
        if (elements.length) onYear(years[elements[0].index]);
      },
      onHover: (event, elements) => {
        const target = event.native?.target as HTMLElement | undefined;
        if (target) target.style.cursor = elements.length ? "pointer" : "default";
      },
      scales: {
        x: { grid: { display: false }, ticks: { maxRotation: 0, autoSkipPadding: 14 } },
        y: {
          beginAtZero: meta.bars,
          title: { display: true, text: meta.unit },
          grid: { color: "#e9e2d0" },
        },
      },
      plugins: {
        tooltip: {
          callbacks: {
            label: (item) =>
              item.raw === null ? "" : `${item.dataset.label}: ${num(item.raw as number, meta.decimals)}`,
            footer: (items) => {
              const row = analysis.annual[items[0].dataIndex];
              return row.complete ? "Click to see this year day by day" : "Incomplete year – not used in the trend";
            },
          },
        },
      },
    }),
    [analysis, metric],
  );

  return (
    <section className="card">
      <div className="card-head">
        <div>
          <h2>{meta.label}</h2>
          <p className="card-sub">
            {analysis.params.start_year}–{analysis.params.end_year} · click a year to inspect it day by day
          </p>
        </div>
        <div className="tabs" role="tablist" aria-label="Indicator">
          {(Object.keys(METRICS) as MetricKey[]).map((key) => (
            <button
              key={key}
              role="tab"
              aria-selected={key === metric}
              className={key === metric ? "tab active" : "tab"}
              onClick={() => onMetric(key)}
            >
              {METRICS[key].tab}
            </button>
          ))}
        </div>
      </div>

      <div className="chart chart-tall">
        <Chart type="bar" data={data} options={options} />
      </div>

      {trend.status === "ok" ? (
        <dl className="trend-stats">
          <div>
            <dt>Verdict (5% level)</dt>
            <dd className={`verdict ${trend.direction}`}>{VERDICT[trend.direction]}</dd>
          </div>
          <div>
            <dt>Mann-Kendall</dt>
            <dd>
              p = {pValue(trend.mann_kendall.p_value)}
              <small>τ = {trend.mann_kendall.tau.toFixed(2)}</small>
            </dd>
          </div>
          <div>
            <dt>Sen's slope</dt>
            <dd>
              {signed(trend.sen_slope * 10, 2)} <span>/ decade</span>
              <small>
                95% CI {signed(trend.sen_slope_ci[0] * 10, 2)} to {signed(trend.sen_slope_ci[1] * 10, 2)}
              </small>
            </dd>
          </div>
          <div>
            <dt>Linear regression</dt>
            <dd>
              {signed(trend.ols.slope * 10, 2)} <span>/ decade</span>
              <small>
                R² = {trend.ols.r_squared.toFixed(2)}, p = {pValue(trend.ols.p_value)}
              </small>
            </dd>
          </div>
          <div>
            <dt>
              {trend.early.from}–{trend.early.to} vs {trend.late.from}–{trend.late.to}
            </dt>
            <dd>
              {num(trend.early.mean, meta.decimals)} → {num(trend.late.mean, meta.decimals)}
              <small>mean of {trend.n} complete years used</small>
            </dd>
          </div>
        </dl>
      ) : (
        <p className="note">
          Only {trend.n} years have a value for this indicator, which is too few to estimate a trend
          (at least 10 are needed).
        </p>
      )}
    </section>
  );
}
