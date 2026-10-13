import type { Analysis, AnalysisRequest, DailyDetail, Meta, Place } from "./types";

const BASE = "/api";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(BASE + path, init);
  } catch {
    throw new Error("Could not reach the server. Check that the API is running.");
  }
  if (!response.ok) {
    let detail = `Request failed (${response.status}).`;
    try {
      const body = await response.json();
      if (typeof body.detail === "string") detail = body.detail;
    } catch {
      // keep the generic message
    }
    throw new Error(detail);
  }
  return response.json() as Promise<T>;
}

export const getMeta = () => request<Meta>("/meta");

export const searchPlaces = (query: string, kind: "city" | "state", signal?: AbortSignal) =>
  request<{ results: Place[] }>(
    `/regions/search?kind=${kind}&q=${encodeURIComponent(query)}`,
    { signal },
  ).then((r) => r.results);

export const runAnalysis = (body: AnalysisRequest) =>
  request<Analysis>("/analyses", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });

export const getAnalysis = (id: string) => request<Analysis>(`/analyses/${id}`);

export const getDaily = (id: string, year: number, cell: number, signal?: AbortSignal) =>
  request<DailyDetail>(`/analyses/${id}/daily?year=${year}&cell=${cell}`, { signal });

export const exportUrl = (id: string, kind: "annual" | "events" | "pdf") =>
  kind === "pdf" ? `${BASE}/analyses/${id}/export.pdf` : `${BASE}/analyses/${id}/export.csv?table=${kind}`;
