import type { LatLngBoundsExpression, LatLngExpression } from "leaflet";
import { useEffect, useState } from "react";
import { CircleMarker, MapContainer, Rectangle, TileLayer, Tooltip, useMap, useMapEvents } from "react-leaflet";
import { COLORS } from "../format";
import type { Cell, Region } from "../types";

type Corner = { lat: number; lon: number };

interface Props {
  mode: "point" | "bbox";
  region: Region | null;
  samplePoints: Cell[];
  onPick: (region: Region) => void;
}

const round = (value: number, digits = 2) => Number(value.toFixed(digits));
// Leaflet lets the world repeat sideways; bring longitudes back to -180..180.
const wrapLon = (lon: number) => ((((lon + 180) % 360) + 360) % 360) - 180;

function boxFrom(a: Corner, b: Corner): Region {
  return {
    type: "bbox",
    south: round(Math.min(a.lat, b.lat)),
    north: round(Math.max(a.lat, b.lat)),
    west: round(Math.min(a.lon, b.lon)),
    east: round(Math.max(a.lon, b.lon)),
  };
}

function bounds(region: Region): LatLngBoundsExpression | null {
  return region.type === "bbox"
    ? [
        [region.south, region.west],
        [region.north, region.east],
      ]
    : null;
}

function ClickHandler({ mode, onPick }: Pick<Props, "mode" | "onPick">) {
  const [first, setFirst] = useState<Corner | null>(null);
  const [hover, setHover] = useState<Corner | null>(null);

  useEffect(() => {
    setFirst(null);
    setHover(null);
  }, [mode]);

  useMapEvents({
    click(event) {
      const here = { lat: event.latlng.lat, lon: wrapLon(event.latlng.lng) };
      if (mode === "point") {
        onPick({ type: "point", lat: round(here.lat), lon: round(here.lon) });
      } else if (!first) {
        setFirst(here);
      } else {
        if (first.lat !== here.lat && first.lon !== here.lon) onPick(boxFrom(first, here));
        setFirst(null);
        setHover(null);
      }
    },
    mousemove(event) {
      if (first) setHover({ lat: event.latlng.lat, lon: wrapLon(event.latlng.lng) });
    },
  });

  if (!first) return null;
  const preview = hover ? boxFrom(first, hover) : null;
  return (
    <>
      <CircleMarker center={[first.lat, first.lon]} radius={4} pathOptions={{ color: COLORS.accent, fillOpacity: 1 }} />
      {preview && preview.type === "bbox" && (
        <Rectangle
          bounds={bounds(preview)!}
          pathOptions={{ color: COLORS.accent, weight: 1.5, dashArray: "5 4", fillOpacity: 0.06 }}
        />
      )}
    </>
  );
}

function FollowRegion({ region }: { region: Region | null }) {
  const map = useMap();
  useEffect(() => {
    if (!region) return;
    if (region.type === "bbox") {
      map.fitBounds(bounds(region)!, { padding: [24, 24], maxZoom: 9 });
    } else {
      const center: LatLngExpression = [region.lat, region.lon];
      map.setView(center, Math.max(map.getZoom(), 6));
    }
  }, [map, region]);
  return null;
}

export default function MapPicker({ mode, region, samplePoints, onPick }: Props) {
  return (
    <div className={`map ${mode === "bbox" ? "map-box" : ""}`}>
      <MapContainer center={[22, 79]} zoom={4} minZoom={2} worldCopyJump scrollWheelZoom>
        <TileLayer
          attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
          url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
        />
        <ClickHandler mode={mode} onPick={onPick} />
        <FollowRegion region={region} />

        {region?.type === "bbox" && (
          <Rectangle
            bounds={bounds(region)!}
            pathOptions={{ color: COLORS.heat, weight: 2, fillColor: COLORS.heat, fillOpacity: 0.08 }}
          />
        )}
        {region?.type === "point" && (
          <CircleMarker
            center={[region.lat, region.lon]}
            radius={8}
            pathOptions={{ color: "#ffffff", weight: 2, fillColor: COLORS.heat, fillOpacity: 1 }}
          />
        )}
        {samplePoints.length > 1 &&
          samplePoints.map((cell, index) => (
            <CircleMarker
              key={`${cell.lat},${cell.lon}`}
              center={[cell.lat, cell.lon]}
              radius={5}
              pathOptions={{ color: "#ffffff", weight: 1.5, fillColor: COLORS.accent, fillOpacity: 1 }}
            >
              <Tooltip>
                Sample point {index + 1}: {cell.lat.toFixed(1)}°, {cell.lon.toFixed(1)}°
              </Tooltip>
            </CircleMarker>
          ))}
      </MapContainer>
    </div>
  );
}
