# Climate Hazard Trend Analyzer

A web application that finds heatwaves in historical daily temperature data for a
city, a state or a custom lat-lon box, and tests whether they are becoming more
frequent, longer or more intense.

- **Frontend:** React, TypeScript, Chart.js, Leaflet
- **Backend:** Python, FastAPI, NumPy, SciPy
- **Database:** MongoDB (with an embedded TinyDB fallback so it runs without any setup)
- **Data:** Open-Meteo Historical Weather API (ERA5 reanalysis, 1940 to about five days ago)

## Running it

Requirements: Python 3.11+ and Node 20+. MongoDB is optional.

```bash
# 1. Backend
cd backend
python -m venv .venv
.venv\Scripts\activate            # macOS / Linux: source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --port 8000

# 2. Frontend (second terminal)
cd frontend
npm install
npm run dev                       # http://localhost:5173
```

**Database.** On start the backend tries `mongodb://localhost:27017`. If nothing
answers within 1.5 seconds it logs a warning and uses TinyDB files in
`backend/data/` instead. To use MongoDB, either run `docker compose up -d` from
the project root or point `MONGODB_URI` at an existing instance (copy
`backend/.env.example` to `backend/.env`). `GET /api/health` reports which store
is in use.

**Single process.** After `npm run build`, the backend serves the built frontend
itself, so the whole app is available on http://localhost:8000.

**Tests.**

```bash
cd backend
pip install -r requirements-dev.txt
pytest
```

55 tests cover the quality checks, the heatwave definition, the trend statistics,
both storage backends and the API (validation, caching, rate limiting, exports).
They use synthetic weather, so they run offline.

## What it does

1. **Choose a region.** Search for a city, search for a state or province, type
   the four edges of a box, or use the map: one click for a point, two clicks for
   opposite corners of a box.
2. **Choose a period**, anywhere between 1940 and the current year.
3. **Optionally change the definition:** percentile (90 to 99), minimum run
   length, a fixed or seasonal threshold, and the baseline period.

The result page shows

- a one-paragraph headline that states the change and whether it is significant;
- yearly bars with a 5-year mean and trend line for six indicators (heatwave days,
  number of events, longest event, mean intensity, peak temperature, annual mean Tmax);
- the test results behind each trend;
- a day-by-day view of any year (click a bar) with the threshold and the events shaded;
- the seasonal distribution, a decade table and a sortable list of every event;
- the limitations that apply to this particular result, and the data-quality counts;
- downloads: PDF report, yearly CSV, events CSV.

Every result has a link of the form `/#/analysis/<id>` that reloads it from the
database.

## Architecture

```
frontend/src
  App.tsx                 form, validation, routing by URL hash
  components/             MapPicker, PlaceSearch, TrendChart, YearDetail, ...
backend/app
  main.py                 app, rate limiting, security headers, error handling
  routes.py               HTTP endpoints
  schemas.py              request validation
  analysis.py             orchestration: region -> cells -> data -> indices -> trends -> store
  weather.py              Open-Meteo client and per-year cache
  cleaning.py             quality control of the daily series
  heatwave.py             thresholds, event detection, yearly indices
  trends.py               linear regression, Mann-Kendall, Sen's slope, rolling mean
  insights.py             sentences and caveats
  exports.py              CSV, PNG, PDF
  storage.py              MongoDB / TinyDB behind one small interface
  upstream.py             the only place that calls third-party APIs
  geocode.py              place search
```

### API

| Method | Path | Purpose |
| --- | --- | --- |
| `POST` | `/api/analyses` | Run an analysis (or return the stored one). Body: region, years, definition. |
| `GET` | `/api/analyses/{id}` | Read a stored analysis from the database. |
| `GET` | `/api/analyses/{id}/daily?year=&cell=` | Daily series for one year, for the drill-down chart. |
| `GET` | `/api/analyses/{id}/export.csv?table=annual\|events` | CSV download. |
| `GET` | `/api/analyses/{id}/export.pdf` | PDF report. |
| `GET` | `/api/analyses/{id}/plot.png?metric=` | Server-rendered trend plot. |
| `GET` | `/api/regions/search?q=&kind=city\|state` | Place search. |
| `GET` | `/api/meta`, `/api/health` | Limits for the form; service status. |

Interactive docs are at http://localhost:8000/docs.

### Database collections

| Collection | One document per | Notes |
| --- | --- | --- |
| `daily_weather` | grid cell and calendar year | `tmax` array with one entry per day, `null` where missing |
| `analyses` | analysis (id = hash of the inputs) | the full JSON result; TTL 30 days, or 1 day if it includes the current or previous year |
| `geocode_cache` | search query | TTL 30 days |

## Data handling

**Source and consistency.** Requests ask for `models=era5` explicitly. The
default "best match" mixes ERA5 with newer, higher-resolution models for recent
years, which would put an artificial step into a multi-decade series.

**Caching.** Daily data is stored per cell and per year. A request for 1990–2020
followed by one for 1980–2020 downloads only 1980–1989. Coordinates are snapped
to 0.1°, which is finer than the 0.25° ERA5 grid, so nearby clicks share a cache
entry. Years older than 90 days are treated as final; the most recent months are
refreshed once a day because ERA5 revises them.

**Units.** Celsius is requested, and the unit in the response is checked rather
than assumed; Fahrenheit and Kelvin are converted, anything else is refused.

**Alignment.** Values are matched to the calendar by date, not by position, so a
response with skipped days cannot shift the rest of the series.

**Quality control** (`cleaning.py`), in this order:

1. Non-numeric values become missing.
2. Values outside −90 to +60 °C are rejected (fill values such as −9999, unit mix-ups).
3. A single day more than 15 °C away from *both* neighbours in the same direction
   is rejected as a spike. A sudden change that persists, such as a cold front, is kept.
4. Gaps of one or two days are filled by linear interpolation and counted.
5. Longer gaps stay missing. A missing day ends a heatwave: filling a long gap
   could invent an event or join two.

A year with less than 90% valid days is shown but left out of the trend
statistics. This is what excludes the current, unfinished year.

ERA5 is gap-free in practice, so these checks rarely fire on live data. They are
exercised by the tests and reported with every result, and they are what a
station-based source such as NOAA GHCN-Daily would need.

## Climate logic

**Definition.** A heatwave is at least *N* consecutive days (default 3) with
daily maximum temperature strictly above the *P*th percentile (default 95) of
daily maxima at that location over a baseline period.

**Two thresholds.**

- *Fixed* (default, as in the brief): one value for the whole year. Heatwaves can
  only occur in the hot season. This measures absolute heat, which is what matters
  for health and infrastructure.
- *Seasonal*: one value per calendar day, from a 15-day window around that day
  pooled over the baseline years. This also finds unusually warm spells in spring
  or winter, and follows the approach of the ETCCDI warm-spell indices.

**Baseline.** By default the percentile comes from the selected period, which is
the literal reading of the brief. That has a consequence worth being clear about:
5% of days exceed the threshold by construction, so the analysis shows how those
days are distributed over the years, not whether there are more of them than in
an earlier climate. Selecting a fixed baseline (1961–1990 or 1991–2020) answers
the second question. The app says which one applies on every result.

**Yearly indices** (after Perkins & Alexander, 2013): number of events, heatwave
days, longest event, mean exceedance above the threshold, hottest heatwave day.
An event that crosses 31 December is counted once, in the year it started, and
its days are credited to the calendar year they fall in.

**Regions.** A city is one grid cell. A state or box is sampled on a regular grid
of up to 3 × 3 points inside its bounding box. Each point is judged against its
own threshold, and the yearly indices are then averaged. Judging each point
locally matters: one regional threshold would let the hottest corner of a state
produce all of its heatwaves.

## Trend analysis

Both tests are run on the complete years:

- **Mann-Kendall with Sen's slope** decides the verdict. Yearly heatwave counts
  are skewed and contain many zeros, so a rank-based test is more appropriate
  than one that assumes normal residuals. The variance includes the correction
  for ties.
- **Linear regression** gives the trend line, R² and a 95% confidence interval
  for the slope.

A 5-year centred mean is drawn for readability. At least 10 years with a value
are required before any trend is reported.

**How the summary sentence is built** (`insights.py`):

- A change is called a trend only if Mann-Kendall is significant at the 5% level.
  Otherwise the sentence says so in plain words.
- The percentage compares the mean of the first ten years with the mean of the
  last ten (first and second half for periods under 20 years). It is not taken
  from the fitted line, which can pass through zero or below.
- No percentage is given when the early mean is under 0.5 days per year.
- Caveats that apply to the specific result are listed beside the findings.

For example, Jaipur 1990–2025 with default settings goes from 12.5 to 16.7
heatwave days per year, but with p = 0.29 the app reports no significant trend
rather than "+34%".

## Security and performance

- **Input validation.** Every field is typed and range-checked by Pydantic;
  unknown fields are rejected. Analysis ids must match `^[a-f0-9]{16}$`. Search
  text is limited to 80 characters of letters, digits and place-name punctuation.
- **Upstream access.** User input reaches third-party APIs only as validated
  numbers or URL-encoded query parameters. Hosts are fixed in an allow-list,
  redirects are not followed, there are timeouts, and 429/5xx responses are
  retried with backoff (honouring `Retry-After`). Calls are spaced per host;
  Nominatim is held to one request per second and is never used for
  search-as-you-type, in line with its usage policy.
- **Rate limiting.** Sliding window per client IP: 120 requests a minute in
  general, 15 a minute for analyses and PDF/PNG rendering. `429` responses carry
  `Retry-After`.
- **Output safety.** Region labels are stripped of control characters, escaped in
  the PDF, and prefixed in CSV when they could be read as a spreadsheet formula.
  React escapes them in the UI.
- **Other.** CORS allow-list, security headers including a content security
  policy, 4 KB body limit, generic 500 responses with details only in the log.
- **Performance.** Three cache layers (daily data, finished analyses, place
  search), all in the database. Identical concurrent requests share one
  computation. Detection is vectorised with NumPy. Responses are gzipped. A
  first-time 36-year city analysis takes about 1.5 s; a 9-point state over 65
  years about 10 s; repeats are served from the database in milliseconds.

## Assumptions and limitations

- **Reanalysis, not stations.** ERA5 is an area average on a 25–30 km grid. It is
  consistent over time, which suits trend analysis, but it smooths urban heat
  islands and reads lower than a city station on extreme days.
- **Bounding boxes.** A state is approximated by its bounding box and at most nine
  sample points, with no area weighting. Proper polygon masks would be the next step.
- **Temperature only.** Many operational definitions also use night-time minimum
  temperature or humidity. This one uses daily maximum only, as the brief specifies.
- **Serial correlation.** Mann-Kendall assumes independent years. Heatwave counts
  have little year-to-year persistence, so no pre-whitening is applied.
- **Southern hemisphere.** Calendar years split the austral summer. Yearly totals
  remain correct, but a July–June year would be the more natural unit there.
- **Limits.** Boxes up to 20° per side, not crossing the antimeridian; periods of
  at least 5 years.
- **Rate limiter and locks are in memory**, which is right for one process. Several
  workers would need a shared store such as Redis.
- **Heatwave only.** The hazard selector lists drought and heavy rainfall as not
  available. Scope was kept to one hazard done properly, as the brief advises.

## With more time

- Polygon boundaries for states with area-weighted averaging.
- A second hazard (heavy rainfall: days above the 95th percentile of wet-day totals).
- A station source (GHCN-Daily) alongside the reanalysis, to compare the two.
- Background jobs with progress for very large first-time requests.
- Frontend component tests.
