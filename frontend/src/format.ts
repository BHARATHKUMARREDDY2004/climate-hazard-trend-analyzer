import type { MetricKey } from "./types";

export const METRICS: Record<MetricKey, { label: string; tab: string; unit: string; decimals: number; bars: boolean }> = {
  days: { label: "Heatwave days", tab: "Days", unit: "days per year", decimals: 1, bars: true },
  events: { label: "Heatwave events", tab: "Frequency", unit: "events per year", decimals: 1, bars: true },
  longest: { label: "Longest heatwave of the year", tab: "Duration", unit: "days", decimals: 1, bars: true },
  mean_excess: { label: "Mean intensity above threshold", tab: "Intensity", unit: "°C above threshold", decimals: 2, bars: false },
  peak_tmax: { label: "Hottest heatwave day", tab: "Peak", unit: "°C", decimals: 1, bars: false },
  mean_tmax: { label: "Annual mean of daily maximum temperature", tab: "Mean Tmax", unit: "°C", decimals: 2, bars: false },
};

export const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

export const COLORS = {
  ink: "#2b2b2b",
  muted: "#6b6558",
  rule: "#d8d0bd",
  navy: "#1f3a5f",
  burgundy: "#7a1f2b",
  burgundySoft: "#c9a3a0",
  forest: "#2f5d50",
  ochre: "#9a6b1f",
  sand: "#b9ad93",
};

export function num(value: number | null | undefined, decimals = 1): string {
  return value === null || value === undefined ? "–" : value.toFixed(decimals);
}

export function signed(value: number, decimals = 1): string {
  const text = value.toFixed(decimals);
  if (Number(text) === 0) return text.replace("-", "");
  return value > 0 ? `+${text}` : text.replace("-", "−");
}

export function pValue(p: number): string {
  return p < 0.001 ? "< 0.001" : p.toFixed(3);
}

export function formatDate(iso: string): string {
  const [y, m, d] = iso.split("-").map(Number);
  return `${d} ${MONTHS[m - 1]} ${y}`;
}

export function dateRange(start: string, end: string): string {
  const [ys, ms, ds] = start.split("-").map(Number);
  const [ye, me, de] = end.split("-").map(Number);
  if (ys === ye && ms === me) return `${ds}–${de} ${MONTHS[me - 1]} ${ye}`;
  if (ys === ye) return `${ds} ${MONTHS[ms - 1]} – ${de} ${MONTHS[me - 1]} ${ye}`;
  return `${formatDate(start)} – ${formatDate(end)}`;
}
