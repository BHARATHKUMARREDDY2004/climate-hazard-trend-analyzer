import { type FormEvent, useEffect, useState } from "react";
import { getAnalysis, getMeta, runAnalysis } from "./api";
import MapPicker from "./components/MapPicker";
import PlaceSearch from "./components/PlaceSearch";
import Results from "./components/Results";
import type { Analysis, Baseline, BoxRegion, Meta, Place, Region, ThresholdMethod } from "./types";

type RegionMode = "city" | "state" | "box";

const MODES: { id: RegionMode; label: string }[] = [
  { id: "city", label: "City" },
  { id: "state", label: "State" },
  { id: "box", label: "Custom box" },
];

const FALLBACK_META: Meta = {
  min_year: 1940,
  max_year: new Date().getFullYear(),
  min_period_years: 5,
  max_box_span_deg: 20,
};

const EMPTY_BOX = { south: "", west: "", north: "", east: "" };

function idFromHash(): string | null {
  const match = window.location.hash.match(/^#\/analysis\/([a-f0-9]{16})$/);
  return match ? match[1] : null;
}

function describe(region: Region): string {
  if (region.label) return region.label;
  if (region.type === "point") return `${region.lat.toFixed(2)}°, ${region.lon.toFixed(2)}°`;
  return `${region.south.toFixed(2)}°, ${region.west.toFixed(2)}° to ${region.north.toFixed(2)}°, ${region.east.toFixed(2)}°`;
}

export default function App() {
  const [meta, setMeta] = useState<Meta>(FALLBACK_META);
  const [mode, setMode] = useState<RegionMode>("city");
  const [region, setRegion] = useState<Region | null>(null);
  const [box, setBox] = useState(EMPTY_BOX);
  const [startYear, setStartYear] = useState("1990");
  const [endYear, setEndYear] = useState(String(FALLBACK_META.max_year - 1));
  const [percentile, setPercentile] = useState(95);
  const [minDuration, setMinDuration] = useState(3);
  const [method, setMethod] = useState<ThresholdMethod>("fixed");
  const [baseline, setBaseline] = useState<Baseline>("period");

  const [analysis, setAnalysis] = useState<Analysis | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    getMeta()
      .then(setMeta)
      .catch(() => undefined);
  }, []);

  // A shared link (#/analysis/<id>) reloads the stored result from the database.
  useEffect(() => {
    function load() {
      const id = idFromHash();
      if (!id || id === analysis?.id) return;
      setLoading(true);
      setError("");
      getAnalysis(id)
        .then((loaded) => {
          setAnalysis(loaded);
          showInForm(loaded);
        })
        .catch((err: Error) => setError(err.message))
        .finally(() => setLoading(false));
    }
    load();
    window.addEventListener("hashchange", load);
    return () => window.removeEventListener("hashchange", load);
  }, [analysis?.id]);

  function showInForm(loaded: Analysis) {
    const { params, region: stored } = loaded;
    const restored = { type: stored.type, ...stored.bounds, label: stored.label } as Region;
    setMode(restored.type === "point" ? "city" : "box");
    setRegion(restored);
    if (restored.type === "bbox") {
      setBox({
        south: String(restored.south),
        west: String(restored.west),
        north: String(restored.north),
        east: String(restored.east),
      });
    }
    setStartYear(String(params.start_year));
    setEndYear(String(params.end_year));
    setPercentile(params.percentile);
    setMinDuration(params.min_duration);
    setMethod(params.threshold_method);
    setBaseline(params.baseline);
  }

  function changeMode(next: RegionMode) {
    setMode(next);
    setRegion(null);
    setBox(EMPTY_BOX);
  }

  function selectPlace(place: Place) {
    if (place.kind === "state" && place.bbox) {
      setRegion({ type: "bbox", ...place.bbox, label: place.label });
    } else {
      setRegion({ type: "point", lat: place.lat, lon: place.lon, label: place.label });
    }
  }

  function pickOnMap(picked: Region) {
    setRegion(picked);
    if (picked.type === "bbox") {
      setBox({
        south: String(picked.south),
        west: String(picked.west),
        north: String(picked.north),
        east: String(picked.east),
      });
    }
  }

  function editBox(side: keyof typeof EMPTY_BOX, value: string) {
    const next = { ...box, [side]: value };
    setBox(next);
    const parsed = Object.fromEntries(Object.entries(next).map(([k, v]) => [k, v === "" ? NaN : Number(v)]));
    const complete = Object.values(parsed).every(Number.isFinite);
    const valid =
      complete &&
      parsed.north > parsed.south &&
      parsed.east > parsed.west &&
      Math.abs(parsed.north) <= 90 &&
      Math.abs(parsed.south) <= 90 &&
      Math.abs(parsed.west) <= 180 &&
      Math.abs(parsed.east) <= 180;
    setRegion(valid ? ({ type: "bbox", ...parsed } as BoxRegion) : null);
  }

  const start = Number(startYear);
  const end = Number(endYear);
  let problem = "";
  if (!region) {
    problem = mode === "box" ? "Draw a box on the map or enter its four edges." : "Choose a place to analyse.";
  } else if (!Number.isInteger(start) || !Number.isInteger(end)) {
    problem = "Enter the start and end year as whole numbers.";
  } else if (start < meta.min_year || end > meta.max_year) {
    problem = `Data is available from ${meta.min_year} to ${meta.max_year}.`;
  } else if (end - start + 1 < meta.min_period_years) {
    problem = `Choose a period of at least ${meta.min_period_years} years.`;
  } else if (
    region.type === "bbox" &&
    (region.north - region.south > meta.max_box_span_deg || region.east - region.west > meta.max_box_span_deg)
  ) {
    problem = `The box may be at most ${meta.max_box_span_deg}° on each side.`;
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (problem || !region) return;
    setLoading(true);
    setError("");
    try {
      const result = await runAnalysis({
        region,
        hazard: "heatwave",
        start_year: start,
        end_year: end,
        percentile,
        min_duration: minDuration,
        threshold_method: method,
        baseline,
      });
      setAnalysis(result);
      window.history.replaceState(null, "", `#/analysis/${result.id}`);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setLoading(false);
    }
  }

  function preset(from: number, to: number) {
    setStartYear(String(Math.max(from, meta.min_year)));
    setEndYear(String(Math.min(to, meta.max_year)));
  }

  const lastFullYear = meta.max_year - 1;

  return (
    <>
      <header className="masthead">
        <div className="wrap">
          <h1>Climate Hazard Trend Analyzer</h1>
          <p>Heatwave frequency, duration and intensity from eight decades of daily temperature records</p>
        </div>
      </header>

      <main className="wrap layout">
        <form className="panel" onSubmit={submit} noValidate>
          <fieldset>
            <legend>1. Region</legend>
            <div className="segmented" role="tablist" aria-label="Region type">
              {MODES.map((m) => (
                <button
                  key={m.id}
                  type="button"
                  role="tab"
                  aria-selected={mode === m.id}
                  className={mode === m.id ? "active" : ""}
                  onClick={() => changeMode(m.id)}
                >
                  {m.label}
                </button>
              ))}
            </div>

            {mode !== "box" && (
              <PlaceSearch kind={mode} maxSpan={meta.max_box_span_deg} onSelect={selectPlace} />
            )}
            {mode === "box" && (
              <div className="box-inputs">
                {(["north", "south", "west", "east"] as const).map((side) => (
                  <label key={side}>
                    <span className="field-label">{side[0].toUpperCase() + side.slice(1)}</span>
                    <input
                      type="number"
                      step="0.01"
                      inputMode="decimal"
                      value={box[side]}
                      placeholder={side === "north" || side === "south" ? "latitude" : "longitude"}
                      onChange={(e) => editBox(side, e.target.value)}
                    />
                  </label>
                ))}
              </div>
            )}

            <MapPicker
              mode={mode === "city" ? "point" : "bbox"}
              region={region}
              samplePoints={analysis?.region.cells ?? []}
              onPick={pickOnMap}
            />
            <p className="field-hint">
              {mode === "city" && "Or click anywhere on the map to pick a point."}
              {mode === "state" && "Or click two opposite corners on the map to outline an area."}
              {mode === "box" && "Click two opposite corners on the map to draw the box."}
            </p>
            {region && (
              <p className="selected">
                <span>Selected</span> {describe(region)}
              </p>
            )}
          </fieldset>

          <fieldset>
            <legend>2. Hazard</legend>
            <label className="field-label" htmlFor="hazard">
              Hazard type
            </label>
            <select id="hazard" defaultValue="heatwave">
              <option value="heatwave">Heatwave</option>
              <option disabled>Drought (not in this version)</option>
              <option disabled>Heavy rainfall (not in this version)</option>
            </select>
          </fieldset>

          <fieldset>
            <legend>3. Time range</legend>
            <div className="year-row">
              <label>
                <span className="field-label">From</span>
                <input
                  type="number"
                  min={meta.min_year}
                  max={meta.max_year}
                  value={startYear}
                  onChange={(e) => setStartYear(e.target.value)}
                />
              </label>
              <label>
                <span className="field-label">To</span>
                <input
                  type="number"
                  min={meta.min_year}
                  max={meta.max_year}
                  value={endYear}
                  onChange={(e) => setEndYear(e.target.value)}
                />
              </label>
            </div>
            <div className="presets">
              <button type="button" onClick={() => preset(1990, 2020)}>
                1990–2020
              </button>
              <button type="button" onClick={() => preset(lastFullYear - 29, lastFullYear)}>
                Last 30 years
              </button>
              <button type="button" onClick={() => preset(meta.min_year, lastFullYear)}>
                Full record
              </button>
            </div>
          </fieldset>

          <details className="advanced">
            <summary>Heatwave definition</summary>
            <label>
              <span className="field-label">Threshold percentile</span>
              <select value={percentile} onChange={(e) => setPercentile(Number(e.target.value))}>
                <option value={90}>90th</option>
                <option value={95}>95th (default)</option>
                <option value={97.5}>97.5th</option>
                <option value={99}>99th</option>
              </select>
            </label>
            <label>
              <span className="field-label">Minimum consecutive days</span>
              <select value={minDuration} onChange={(e) => setMinDuration(Number(e.target.value))}>
                {[2, 3, 4, 5, 6, 7].map((d) => (
                  <option key={d} value={d}>
                    {d}
                    {d === 3 ? " (default)" : ""}
                  </option>
                ))}
              </select>
            </label>
            <label>
              <span className="field-label">Threshold type</span>
              <select value={method} onChange={(e) => setMethod(e.target.value as ThresholdMethod)}>
                <option value="fixed">One value for the whole year</option>
                <option value="seasonal">Relative to the time of year</option>
              </select>
            </label>
            <label>
              <span className="field-label">Baseline for the percentile</span>
              <select value={baseline} onChange={(e) => setBaseline(e.target.value as Baseline)}>
                <option value="period">The selected period</option>
                <option value="1961-1990">1961–1990 (fixed)</option>
                <option value="1991-2020">1991–2020 (fixed)</option>
              </select>
            </label>
            <p className="field-hint">
              A fixed baseline measures change against an earlier climate. The seasonal threshold also finds
              unusually warm spells outside summer.
            </p>
          </details>

          <button type="submit" className="button wide" disabled={loading || Boolean(problem)}>
            {loading ? "Analysing…" : "Analyse heatwaves"}
          </button>
          {problem && <p className="field-hint center">{problem}</p>}
        </form>

        <div className="content" aria-live="polite">
          {error && (
            <div className="alert" role="alert">
              <strong>That did not work.</strong> {error}
            </div>
          )}
          {loading && (
            <div className="status">
              <div className="spinner" aria-hidden="true" />
              <p>
                Collecting daily temperatures and detecting heatwaves. A location that has not been analysed
                before takes a few seconds while its history is downloaded and cached.
              </p>
            </div>
          )}
          {!loading && analysis && <Results analysis={analysis} />}
          {!loading && !analysis && !error && (
            <section className="card intro">
              <h2>How it works</h2>
              <ol>
                <li>Pick a city, a state, or draw your own box on the map.</li>
                <li>Choose the years to study. Thirty years or more gives a dependable trend.</li>
                <li>
                  The analyzer finds every heatwave – three or more consecutive days hotter than the 95th
                  percentile for that place – and tests whether they are becoming more frequent, longer or
                  more intense.
                </li>
              </ol>
              <p>
                Results state plainly when a change is not statistically significant, and list the limits of
                the data alongside the findings.
              </p>
            </section>
          )}
        </div>
      </main>

      <footer className="wrap colophon">
        Weather data by <a href="https://open-meteo.com/">Open-Meteo</a> (ERA5 reanalysis, Copernicus Climate
        Change Service). Place search by Open-Meteo and <a href="https://nominatim.org/">Nominatim</a>. Map ©
        OpenStreetMap contributors.
      </footer>
    </>
  );
}
