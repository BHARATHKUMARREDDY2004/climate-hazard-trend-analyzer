import { type FormEvent, useEffect, useRef, useState } from "react";
import { searchPlaces } from "../api";
import type { Place } from "../types";

interface Props {
  kind: "city" | "state";
  maxSpan: number;
  onSelect: (place: Place) => void;
}

export default function PlaceSearch({ kind, maxSpan, onSelect }: Props) {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<Place[] | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const pending = useRef<AbortController | null>(null);
  // Set when the text was filled in by choosing a result, so it does not search again.
  const skipNext = useRef(false);

  async function search(text: string) {
    pending.current?.abort();
    const controller = new AbortController();
    pending.current = controller;
    setBusy(true);
    setError("");
    try {
      setResults(await searchPlaces(text, kind, controller.signal));
    } catch (err) {
      if (controller.signal.aborted) return;
      setResults(null);
      setError((err as Error).message);
    } finally {
      if (!controller.signal.aborted) setBusy(false);
    }
  }

  useEffect(() => {
    setQuery("");
    setResults(null);
    setError("");
  }, [kind]);

  // Cities are suggested while typing. State lookups go to Nominatim, whose
  // usage policy does not allow search-as-you-type, so those wait for Enter.
  useEffect(() => {
    if (skipNext.current) {
      skipNext.current = false;
      return;
    }
    if (kind !== "city" || query.trim().length < 3) return;
    const timer = setTimeout(() => search(query.trim()), 350);
    return () => clearTimeout(timer);
  }, [query, kind]);

  function submit(event: FormEvent) {
    event.preventDefault();
    if (query.trim().length >= 2) search(query.trim());
  }

  function choose(place: Place) {
    if (place.too_large) return;
    skipNext.current = true;
    setQuery(place.label);
    setResults(null);
    onSelect(place);
  }

  return (
    <div className="search">
      <form onSubmit={submit} role="search">
        <label htmlFor="place" className="field-label">
          {kind === "city" ? "City or town" : "State or province"}
        </label>
        <div className="search-row">
          <input
            id="place"
            type="search"
            value={query}
            maxLength={80}
            autoComplete="off"
            placeholder={kind === "city" ? "e.g. Jaipur" : "e.g. Rajasthan"}
            onChange={(e) => setQuery(e.target.value)}
          />
          <button type="submit" className="button-secondary" disabled={busy || query.trim().length < 2}>
            {busy ? "Searching…" : "Search"}
          </button>
        </div>
      </form>

      {error && <p className="field-error">{error}</p>}
      {results && results.length === 0 && <p className="field-hint">No matching places found.</p>}
      {results && results.length > 0 && (
        <ul className="search-results">
          {results.map((place) => (
            <li key={`${place.label}-${place.lat}-${place.lon}`}>
              <button type="button" onClick={() => choose(place)} disabled={place.too_large}>
                <span>{place.label}</span>
                <small>
                  {place.too_large
                    ? `larger than ${maxSpan}° – draw a box inside it instead`
                    : `${place.lat.toFixed(2)}°, ${place.lon.toFixed(2)}°`}
                </small>
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
