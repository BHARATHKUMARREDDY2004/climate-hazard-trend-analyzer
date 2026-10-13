import { useMemo, useState } from "react";
import { dateRange, num } from "../format";
import type { Analysis, HeatwaveEvent } from "../types";

type SortKey = "start" | "duration" | "peak_tmax" | "mean_excess" | "severity";

const COLUMNS: { key: SortKey; label: string; title?: string }[] = [
  { key: "start", label: "Dates" },
  { key: "duration", label: "Days" },
  { key: "peak_tmax", label: "Peak °C" },
  { key: "mean_excess", label: "Mean excess °C", title: "Average degrees above the threshold" },
  { key: "severity", label: "Severity", title: "Sum of degrees above the threshold over the event" },
];

const PAGE = 10;

interface Props {
  analysis: Analysis;
  onYear: (year: number) => void;
}

export default function EventsTable({ analysis, onYear }: Props) {
  const [sortKey, setSortKey] = useState<SortKey>("severity");
  const [descending, setDescending] = useState(true);
  const [showAll, setShowAll] = useState(false);
  const multiple = analysis.region.cells.length > 1;

  const sorted = useMemo(() => {
    const direction = descending ? -1 : 1;
    return [...analysis.events].sort((a: HeatwaveEvent, b: HeatwaveEvent) =>
      a[sortKey] < b[sortKey] ? -direction : a[sortKey] > b[sortKey] ? direction : 0,
    );
  }, [analysis.events, sortKey, descending]);

  function sortBy(key: SortKey) {
    if (key === sortKey) setDescending(!descending);
    else {
      setSortKey(key);
      setDescending(true);
    }
  }

  const rows = showAll ? sorted : sorted.slice(0, PAGE);

  return (
    <section className="card">
      <h2>Heatwave events</h2>
      <p className="card-sub">
        {analysis.events.length} event{analysis.events.length === 1 ? "" : "s"} detected
        {multiple && " across all sample points"} · click a column to sort
      </p>
      {analysis.events.length === 0 ? (
        <p className="note">No event met the definition in this period.</p>
      ) : (
        <>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  {COLUMNS.map((column) => (
                    <th
                      key={column.key}
                      title={column.title}
                      className={column.key === "start" ? "" : "numeric"}
                      aria-sort={sortKey === column.key ? (descending ? "descending" : "ascending") : "none"}
                    >
                      <button onClick={() => sortBy(column.key)}>
                        {column.label}
                        <span aria-hidden="true">{sortKey === column.key ? (descending ? " ▾" : " ▴") : ""}</span>
                      </button>
                    </th>
                  ))}
                  {multiple && <th>Sample point</th>}
                </tr>
              </thead>
              <tbody>
                {rows.map((event) => (
                  <tr key={`${event.cell}-${event.start}`}>
                    <td>
                      <button className="link" onClick={() => onYear(Number(event.start.slice(0, 4)))}>
                        {dateRange(event.start, event.end)}
                      </button>
                    </td>
                    <td className="numeric">{event.duration}</td>
                    <td className="numeric">{num(event.peak_tmax)}</td>
                    <td className="numeric">{num(event.mean_excess, 2)}</td>
                    <td className="numeric">{num(event.severity)}</td>
                    {multiple && <td>Point {event.cell + 1}</td>}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {sorted.length > PAGE && (
            <button className="button-secondary" onClick={() => setShowAll(!showAll)}>
              {showAll ? "Show top 10 only" : `Show all ${sorted.length}`}
            </button>
          )}
        </>
      )}
    </section>
  );
}
