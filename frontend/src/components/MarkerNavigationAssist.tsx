import { useState } from 'react';
import { useFreshMarkerFrame } from '@/hooks/useFreshMarkerFrame';
import type { MarkerDetection } from '@/types/drone';

function markerKey(marker: MarkerDetection): string {
  return `${marker.marker_type}:${marker.marker_id}`;
}

function markerLabel(marker: MarkerDetection): string {
  if (marker.marker_type === 'aruco') return `ArUco #${marker.marker_id}`;
  if (marker.payload) {
    const suffix = marker.payload_truncated ? '…' : '';
    return `QR: ${marker.payload.slice(0, 40)}${suffix}`;
  }
  return `QR #${marker.marker_id}`;
}

function targetOffset(marker: MarkerDetection): string {
  const centerX = (marker.x_min + marker.x_max) / 2;
  const centerY = (marker.y_min + marker.y_max) / 2;
  const horizontal =
    Math.abs(centerX - 0.5) < 0.08
      ? null
      : centerX < 0.5
        ? 'left'
        : 'right';
  const vertical =
    Math.abs(centerY - 0.5) < 0.08
      ? null
      : centerY < 0.5
        ? 'above'
        : 'below';
  const offset = [vertical, horizontal].filter(Boolean).join(' and ');

  return offset ? `${offset} of frame center` : 'near frame center';
}

export default function MarkerNavigationAssist() {
  const frame = useFreshMarkerFrame();
  const [selectedMarkerKey, setSelectedMarkerKey] = useState<string | null>(null);
  const markers = frame?.data.markers ?? [];
  const selectedMarker = markers.find(
    (marker) => markerKey(marker) === selectedMarkerKey,
  );
  const status = !frame
    ? 'Waiting for video'
    : markers.length > 0
      ? `${markers.length} marker${markers.length === 1 ? '' : 's'} detected`
      : 'No QR/ArUco markers detected';

  return (
    <>
      {frame && markers.length > 0 && (
        <svg
          role="img"
          aria-label="QR and ArUco marker overlay"
          viewBox={`0 0 ${frame.data.frame_width} ${frame.data.frame_height}`}
          preserveAspectRatio="xMidYMid slice"
          className="fixed inset-0 z-[1] h-full w-full pointer-events-none"
        >
          <title>QR and ArUco marker overlay</title>
          {markers.map((marker) => {
            const x = marker.x_min * frame.data.frame_width;
            const y = marker.y_min * frame.data.frame_height;
            const width =
              (marker.x_max - marker.x_min) * frame.data.frame_width;
            const height =
              (marker.y_max - marker.y_min) * frame.data.frame_height;
            const isSelected = markerKey(marker) === selectedMarkerKey;
            const label = markerLabel(marker);

            return (
              <g key={markerKey(marker)} aria-label={label}>
                <rect
                  x={x}
                  y={y}
                  width={width}
                  height={height}
                  fill="none"
                  stroke={isSelected ? '#38bdf8' : '#fbbf24'}
                  strokeWidth={isSelected ? '3' : '2'}
                  vectorEffect="non-scaling-stroke"
                />
                <text
                  x={x}
                  y={Math.max(y - 6, 12)}
                  fill="white"
                  fontSize="10"
                  fontWeight="700"
                  paintOrder="stroke"
                  stroke="#111827"
                  strokeLinejoin="round"
                  strokeWidth="3"
                >
                  {label.slice(0, 32)}
                </text>
              </g>
            );
          })}
        </svg>
      )}

      <section
        aria-label="Marker navigation assistance"
        className="fixed right-3 top-1/2 z-[3] w-[min(90vw,260px)] -translate-y-1/2 hud-panel !p-3 pointer-events-auto"
      >
        <h2 className="hud-label mb-2 text-white">Marker Guidance</h2>
        <p className="text-xs text-white/60">{status}</p>

        {selectedMarkerKey !== null && (
          <div className="mt-2 rounded border border-amber-300/20 bg-amber-300/10 px-2 py-1.5">
            <div className="text-xs font-semibold text-amber-100">
              Target: {selectedMarker ? markerLabel(selectedMarker) : 'not detected'}
            </div>
            {selectedMarker && (
              <div className="mt-0.5 text-[11px] text-white/70">
                {targetOffset(selectedMarker)}
              </div>
            )}
          </div>
        )}

        {markers.length > 0 && (
          <div className="mt-2 max-h-[20vh] space-y-1 overflow-y-auto">
            {markers.slice(0, 6).map((marker) => {
              const key = markerKey(marker);
              const isSelected = key === selectedMarkerKey;
              return (
                <button
                  key={key}
                  type="button"
                  aria-pressed={isSelected}
                  className="control-btn w-full !justify-between px-2 py-1.5 text-left text-xs"
                  onClick={() =>
                    setSelectedMarkerKey(isSelected ? null : key)
                  }
                >
                  <span className="truncate">{markerLabel(marker)}</span>
                  <span className="ml-2 shrink-0 text-white/60">
                    {marker.marker_type === 'qr' ? 'QR' : 'ArUco'}
                  </span>
                </button>
              );
            })}
            {markers.length > 6 && (
              <p className="text-[10px] text-white/50">
                {markers.length - 6} more markers in frame
              </p>
            )}
          </div>
        )}

        {selectedMarkerKey !== null && (
          <button
            type="button"
            className="mt-2 w-full text-left text-[11px] text-amber-100 underline underline-offset-2"
            onClick={() => setSelectedMarkerKey(null)}
          >
            Clear target
          </button>
        )}
        <p className="mt-2 border-t border-white/10 pt-2 text-[10px] leading-relaxed text-white/50">
          Visual guidance only. Align manually; no RC commands or autonomous
          movement. Marker size is not calibrated for distance.
        </p>
      </section>
    </>
  );
}
