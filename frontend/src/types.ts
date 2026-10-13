export type PointRegion = { type: "point"; lat: number; lon: number; label?: string };
export type BoxRegion = {
  type: "bbox";
  south: number;
  north: number;
  west: number;
  east: number;
  label?: string;
};
export type Region = PointRegion | BoxRegion;

export type ThresholdMethod = "fixed" | "seasonal";
export type Baseline = "period" | "1961-1990" | "1991-2020";

export interface AnalysisRequest {
  region: Region;
  hazard: "heatwave";
  start_year: number;
  end_year: number;
  percentile: number;
  min_duration: number;
  threshold_method: ThresholdMethod;
  baseline: Baseline;
}

export interface Place {
  kind: "city" | "state";
  label: string;
  lat: number;
  lon: number;
  bbox?: { south: number; north: number; west: number; east: number };
  too_large?: boolean;
}

export type MetricKey = "days" | "events" | "longest" | "mean_excess" | "peak_tmax" | "mean_tmax";

export interface AnnualRow {
  year: number;
  events: number;
  days: number;
  longest: number;
  mean_excess: number | null;
  peak_tmax: number | null;
  hot_days: number;
  mean_tmax: number | null;
  max_tmax: number | null;
  coverage: number;
  complete: boolean;
}

export interface TrendBlock {
  from: number;
  to: number;
  mean: number;
}

export type Trend =
  | { status: "insufficient"; n: number }
  | {
      status: "ok";
      n: number;
      direction: "increasing" | "decreasing" | "no_significant_trend";
      ols: { slope: number; intercept: number; r_squared: number; p_value: number; slope_ci: [number, number] };
      mann_kendall: { s: number; z: number; p_value: number; tau: number };
      sen_slope: number;
      sen_slope_ci: [number, number];
      early: TrendBlock;
      late: TrendBlock;
      change: number;
    };

export interface HeatwaveEvent {
  start: string;
  end: string;
  duration: number;
  peak_tmax: number;
  mean_tmax: number;
  mean_excess: number;
  severity: number;
  cell: number;
}

export interface Cell {
  lat: number;
  lon: number;
  grid_lat: number | null;
  grid_lon: number | null;
  elevation: number | null;
}

export interface Insight {
  kind: "headline" | "finding" | "caution";
  text: string;
}

export interface Analysis {
  id: string;
  created_at: number;
  served_from?: "computed" | "database";
  compute_seconds: number;
  params: {
    hazard: string;
    start_year: number;
    end_year: number;
    percentile: number;
    min_duration: number;
    threshold_method: ThresholdMethod;
    baseline: Baseline;
    baseline_years: [number, number];
  };
  region: { type: "point" | "bbox"; label: string; bounds: Record<string, number>; cells: Cell[] };
  threshold: {
    method: ThresholdMethod;
    mean_value: number | null;
    min_value: number | null;
    max_value: number | null;
  };
  annual: AnnualRow[];
  rolling: Record<MetricKey, (number | null)[]>;
  trends: Record<MetricKey, Trend>;
  decadal: { decade: string; years: number; days: number; events: number; longest: number; mean_tmax: number }[];
  monthly: Record<"early" | "late", { from: number; to: number; days: number[] }>;
  events: HeatwaveEvent[];
  summary: {
    complete_years: number;
    total_events: number | null;
    mean_days_per_year: number | null;
    mean_events_per_year: number | null;
    years_with_heatwave: number;
    longest_event: HeatwaveEvent | null;
    hottest_event: HeatwaveEvent | null;
  };
  quality: {
    missing: number;
    out_of_range: number;
    spike: number;
    interpolated: number;
    unfilled: number;
    total_days: number;
    valid_share: number;
    incomplete_years: number[];
    cell_years_requested: number;
    cell_years_from_cache: number;
  };
  source: { name: string; variable: string; unit: string };
  insights: Insight[];
}

export interface DailyDetail {
  year: number;
  cell: number;
  lat: number;
  lon: number;
  dates: string[];
  tmax: (number | null)[];
  threshold: number[];
  interpolated: number[];
  events: HeatwaveEvent[];
}

export interface Meta {
  min_year: number;
  max_year: number;
  min_period_years: number;
  max_box_span_deg: number;
}
