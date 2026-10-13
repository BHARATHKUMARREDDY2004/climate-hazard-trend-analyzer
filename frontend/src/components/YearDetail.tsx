import type { ChartData, ChartOptions } from "chart.js";
import { useEffect, useMemo, useState } from "react";
import { Line } from "react-chartjs-2";
import { getDaily } from "../api";
import { COLORS, MONTHS, dateRange, formatDate, num } from "../format";
import type { Analysis, DailyDetail } from "../types";

interface Props {
  analysis: Analysis;
  year: number;
  onYear: (year: number) => void;
}

export default function YearDetail({ analysis, year, onYear }: Props) {
  const cells = analysis.region.cells;
  const [cell, setCell] = useState(0);
  const [detail, setDetail] = useState<DailyDetail | null>(null);
  const [error, setError] = useState("");

  useEffect(() => setCell(0), [analysis.id]);

  useEffect(() => {
    const controller = new AbortController();
    setError("");
    getDaily(analysis.id, year, cell, controller.signal)
      .then(setDetail)
      .catch((err: Error) => {
        if (!controller.signal.aborted) setError(err.message);
      });
    return () => controller.abort();
  }, [analysis.id, year, cell]);

  const data = useMemo<ChartData<"line">>(() => {
    if (!detail) return { labels: [], datasets: [] };
    const inEvent = detail.dates.map((day) => detail.events.some((e) => day >= e.start && day <= e.end));
    return {
      labels: detail.dates,
      datasets: [
        {
          label: "Heatwave days",
          data: detail.tmax.map((v, i) => (inEvent[i] ? v : null)),
          borderColor: COLORS.burgundy,
          backgroundColor: "rgba(122, 31, 43, 0.22)",
          borderWidth: 2.5,
          pointRadius: 0,
          fill: { target: 2, above: "rgba(122, 31, 43, 0.22)", below: "transparent" },
        },
        {
          label: "Daily maximum temperature",
          data: detail.tmax,
          borderColor: COLORS.sand,
          backgroundColor: COLORS.sand,
          borderWidth: 1.2,
          pointRadius: 0,
        },
        {
          label: `Threshold (${analysis.params.percentile}th percentile)`,
          data: detail.threshold,
          borderColor: COLORS.navy,
          backgroundColor: COLORS.navy,
          borderWidth: 1.5,
          borderDash: [6, 4],
          pointRadius: 0,
        },
      ],
    };
  }, [detail, analysis.params.percentile]);

  const options = useMemo<ChartOptions<"line">>(
    () => ({
      interaction: { mode: "index", intersect: false },
      scales: {
        x: {
          grid: { display: false },
          ticks: {
            autoSkip: false,
            maxRotation: 0,
            // one label per month, on the first day
            callback(_value, index) {
              const day = detail?.dates[index];
              return day && day.endsWith("-01") ? MONTHS[Number(day.slice(5, 7)) - 1] : null;
            },
          },
        },
        y: { title: { display: true, text: "°C" }, grid: { color: "#e9e2d0" } },
      },
      plugins: {
        tooltip: {
          filter: (item) => item.raw !== null,
          callbacks: {
            title: (items) => (items.length ? formatDate(items[0].label) : ""),
            label: (item) => `${item.dataset.label}: ${num(item.raw as number)} °C`,
          },
        },
      },
    }),
    [detail],
  );

  const { start_year, end_year } = analysis.params;

  return (
    <section className="card">
      <div className="card-head">
        <div>
          <h2>{year}, day by day</h2>
          <p className="card-sub">
            Daily maximum temperature against the heatwave threshold
            {cells.length > 1 && ` at sample point ${cell + 1}`}
          </p>
        </div>
        <div className="stepper">
          {cells.length > 1 && (
            <select value={cell} onChange={(e) => setCell(Number(e.target.value))} aria-label="Sample point">
              {cells.map((c, index) => (
                <option key={index} value={index}>
                  Point {index + 1} ({c.lat.toFixed(1)}°, {c.lon.toFixed(1)}°)
                </option>
              ))}
            </select>
          )}
          <button className="button-secondary" disabled={year <= start_year} onClick={() => onYear(year - 1)}>
            ← {year - 1}
          </button>
          <button className="button-secondary" disabled={year >= end_year} onClick={() => onYear(year + 1)}>
            {year + 1} →
          </button>
        </div>
      </div>

      {error ? (
        <p className="field-error">{error}</p>
      ) : (
        <>
          <div className="chart">
            <Line data={data} options={options} />
          </div>
          {detail && detail.year === year && (
            <p className="note">
              {detail.events.length === 0
                ? `No heatwave met the definition in ${year}.`
                : detail.events
                    .map((e) => `${dateRange(e.start, e.end)} (${e.duration} days, peak ${num(e.peak_tmax)} °C)`)
                    .join(" · ")}
            </p>
          )}
        </>
      )}
    </section>
  );
}
