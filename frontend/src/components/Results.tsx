import { useEffect, useState } from "react";
import { exportUrl } from "../api";
import { METRICS, dateRange, num, pValue, signed } from "../format";
import type { Analysis, MetricKey } from "../types";
import EventsTable from "./EventsTable";
import SeasonChart from "./SeasonChart";
import TrendChart from "./TrendChart";
import YearDetail from "./YearDetail";

function thresholdText(analysis: Analysis): string {
  const { threshold, params } = analysis;
  const pct = `${params.percentile}th percentile`;
  if (threshold.method === "seasonal") return `${pct} for each calendar day`;
  if (threshold.min_value === threshold.max_value) return `${num(threshold.mean_value)} °C (${pct})`;
  return `${num(threshold.min_value)}–${num(threshold.max_value)} °C (${pct}, varies by sample point)`;
}

function mostAffectedYear(analysis: Analysis): number {
  const complete = analysis.annual.filter((row) => row.complete);
  const rows = complete.length ? complete : analysis.annual;
  return rows.reduce((best, row) => (row.days > best.days ? row : best), rows[0]).year;
}

function Tiles({ analysis }: { analysis: Analysis }) {
  const days = analysis.trends.days;
  const { longest_event, hottest_event, years_with_heatwave, complete_years } = analysis.summary;
  return (
    <div className="tiles">
      <div className="tile">
        <span className="tile-label">Heatwave days per year</span>
        {days.status === "ok" ? (
          <>
            <span className="tile-value">
              {num(days.early.mean)} <span className="arrow">→</span> {num(days.late.mean)}
            </span>
            <span className="tile-note">
              {days.early.from}–{days.early.to} vs {days.late.from}–{days.late.to}
            </span>
          </>
        ) : (
          <>
            <span className="tile-value">{num(analysis.summary.mean_days_per_year)}</span>
            <span className="tile-note">average over the period</span>
          </>
        )}
      </div>
      <div className="tile">
        <span className="tile-label">Trend in heatwave days</span>
        {days.status === "ok" ? (
          <>
            <span className="tile-value">
              {signed(days.sen_slope * 10)} <small>/ decade</small>
            </span>
            <span className="tile-note">
              <span className={`badge ${days.direction}`}>
                {days.direction === "no_significant_trend" ? "Not significant" : "Significant"}
              </span>{" "}
              p = {pValue(days.mann_kendall.p_value)}
            </span>
          </>
        ) : (
          <>
            <span className="tile-value">–</span>
            <span className="tile-note">too few years</span>
          </>
        )}
      </div>
      <div className="tile">
        <span className="tile-label">Years with a heatwave</span>
        <span className="tile-value">
          {years_with_heatwave} <small>of {complete_years}</small>
        </span>
        <span className="tile-note">complete years in the period</span>
      </div>
      <div className="tile">
        <span className="tile-label">Longest heatwave</span>
        <span className="tile-value">
          {longest_event ? longest_event.duration : "–"} <small>days</small>
        </span>
        <span className="tile-note">{longest_event ? dateRange(longest_event.start, longest_event.end) : "none detected"}</span>
      </div>
      <div className="tile">
        <span className="tile-label">Hottest heatwave day</span>
        <span className="tile-value">
          {hottest_event ? num(hottest_event.peak_tmax) : "–"} <small>°C</small>
        </span>
        <span className="tile-note">
          {hottest_event ? `during ${dateRange(hottest_event.start, hottest_event.end)}` : "none detected"}
        </span>
      </div>
    </div>
  );
}

function DecadeTable({ analysis }: { analysis: Analysis }) {
  return (
    <section className="card">
      <h2>By decade</h2>
      <p className="card-sub">Averages per year over the complete years in each decade</p>
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Decade</th>
              <th className="numeric" title="Complete years in the decade">Yrs</th>
              <th className="numeric">Days/yr</th>
              <th className="numeric">Events/yr</th>
              <th className="numeric" title="Longest heatwave, days">Longest</th>
              <th className="numeric" title="Mean of daily maximum temperature">Tmax °C</th>
            </tr>
          </thead>
          <tbody>
            {analysis.decadal.map((row) => (
              <tr key={row.decade}>
                <td>{row.decade}</td>
                <td className="numeric">{row.years}</td>
                <td className="numeric">{num(row.days)}</td>
                <td className="numeric">{num(row.events)}</td>
                <td className="numeric">{num(row.longest, 0)}</td>
                <td className="numeric">{num(row.mean_tmax, 2)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {analysis.decadal.some((row) => row.years < 10) && (
        <p className="note">Decades with fewer than 10 years are partial and not directly comparable.</p>
      )}
    </section>
  );
}

function Quality({ analysis }: { analysis: Analysis }) {
  const q = analysis.quality;
  const n = (value: number) => value.toLocaleString("en-GB");
  const { params } = analysis;
  return (
    <section className="card">
      <h2>Method and data quality</h2>
      <div className="columns">
        <div>
          <h3>Definition used</h3>
          <ul className="plain">
            <li>
              A heatwave is {params.min_duration} or more consecutive days with a daily maximum temperature above
              the threshold.
            </li>
            <li>Threshold: {thresholdText(analysis)}.</li>
            <li>
              Baseline for the percentile: {params.baseline_years[0]}–{params.baseline_years[1]}
              {params.baseline === "period" && " (the selected period)"}.
            </li>
            <li>
              Trends: Mann-Kendall test with Sen's slope for the verdict, least-squares regression for the line.
              Significance level 5%.
            </li>
            <li>Source: {analysis.source.name}.</li>
          </ul>
        </div>
        <div>
          <h3>Data checks</h3>
          <table className="compact">
            <tbody>
              <tr>
                <td>Daily values examined</td>
                <td className="numeric">{n(q.total_days)}</td>
              </tr>
              <tr>
                <td>Missing from the source</td>
                <td className="numeric">{n(q.missing)}</td>
              </tr>
              <tr>
                <td>Rejected as physically implausible</td>
                <td className="numeric">{n(q.out_of_range)}</td>
              </tr>
              <tr>
                <td>Rejected as isolated spikes</td>
                <td className="numeric">{n(q.spike)}</td>
              </tr>
              <tr>
                <td>Filled by interpolation (gaps of 1–2 days)</td>
                <td className="numeric">{n(q.interpolated)}</td>
              </tr>
              <tr>
                <td>Left missing</td>
                <td className="numeric">{n(q.unfilled)}</td>
              </tr>
              <tr>
                <td>Years excluded from trends</td>
                <td className="numeric">{q.incomplete_years.length ? q.incomplete_years.join(", ") : "none"}</td>
              </tr>
            </tbody>
          </table>
          <p className="note">
            {q.cell_years_from_cache} of {q.cell_years_requested} location-years came from the local cache
            {analysis.served_from === "database" ? "; this result was read from the database." : "."}
          </p>
        </div>
      </div>
    </section>
  );
}

export default function Results({ analysis }: { analysis: Analysis }) {
  const [metric, setMetric] = useState<MetricKey>("days");
  const [year, setYear] = useState(() => mostAffectedYear(analysis));

  useEffect(() => {
    setYear(mostAffectedYear(analysis));
  }, [analysis.id]);

  const headline = analysis.insights.find((i) => i.kind === "headline");
  const findings = analysis.insights.filter((i) => i.kind === "finding");
  const cautions = analysis.insights.filter((i) => i.kind === "caution");
  const { params } = analysis;

  return (
    <div className="results">
      <section className="card headline">
        <p className="eyebrow">
          {analysis.region.label} · {params.start_year}–{params.end_year}
        </p>
        <p className="headline-text">{headline?.text}</p>
        <p className="headline-meta">
          Heatwave: at least {params.min_duration} consecutive days above {thresholdText(analysis)}
        </p>
        <div className="actions">
          <a className="button" href={exportUrl(analysis.id, "pdf")} download>
            Download PDF report
          </a>
          <a className="button-secondary" href={exportUrl(analysis.id, "annual")} download>
            Yearly data (CSV)
          </a>
          <a className="button-secondary" href={exportUrl(analysis.id, "events")} download>
            Events (CSV)
          </a>
        </div>
      </section>

      <Tiles analysis={analysis} />

      <TrendChart analysis={analysis} metric={metric} selectedYear={year} onMetric={setMetric} onYear={setYear} />
      <YearDetail analysis={analysis} year={year} onYear={setYear} />

      <div className="two-up">
        <section className="card">
          <h2>What the data shows</h2>
          <ul className="findings">
            {findings.map((item) => (
              <li key={item.text}>{item.text}</li>
            ))}
          </ul>
        </section>
        <section className="card caution">
          <h2>How far to trust it</h2>
          <ul className="findings">
            {cautions.map((item) => (
              <li key={item.text}>{item.text}</li>
            ))}
          </ul>
        </section>
      </div>

      <div className="two-up">
        <SeasonChart analysis={analysis} />
        <DecadeTable analysis={analysis} />
      </div>

      <EventsTable analysis={analysis} onYear={setYear} />
      <Quality analysis={analysis} />

      <p className="footnote">
        Indicator shown above: {METRICS[metric].label.toLowerCase()}. Analysis {analysis.id}, computed in{" "}
        {analysis.compute_seconds} s.
      </p>
    </div>
  );
}
