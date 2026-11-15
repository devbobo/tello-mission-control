import { useEffect, useState } from 'react';
import { useFreshOdometryFrame } from '@/hooks/useFreshOdometryFrame';

interface MapPoint {
  frameId: number;
  x: number;
  y: number;
}

interface Coordinate {
  x: number;
  y: number;
}

const ORIGIN: MapPoint = { frameId: 0, x: 0, y: 0 };
const MAX_TRAIL_POINTS = 32;

function mapCoordinates(points: Coordinate[]) {
  const xs = points.map((point) => point.x);
  const ys = points.map((point) => point.y);
  const minX = Math.min(...xs);
  const maxX = Math.max(...xs);
  const minY = Math.min(...ys);
  const maxY = Math.max(...ys);
  const extent = Math.max(maxX - minX, maxY - minY, 0.02);
  const scale = 64 / extent;
  const centerX = (minX + maxX) / 2;
  const centerY = (minY + maxY) / 2;

  return points.map((point) => ({
    x: 50 + (point.x - centerX) * scale,
    y: 50 - (point.y - centerY) * scale,
  }));
}

export default function VisualOdometryMap() {
  const frame = useFreshOdometryFrame();
  const [trail, setTrail] = useState<MapPoint[]>([]);

  useEffect(() => {
    if (!frame) return;

    const point = {
      frameId: frame.data.frame_id,
      x: frame.data.position_x,
      y: frame.data.position_y,
    };
    setTrail((previous) => {
      const last = previous[previous.length - 1];
      if (last?.frameId === point.frameId) return previous;
      if (last && point.frameId < last.frameId) {
        return frame.data.tracking_valid ? [ORIGIN, point] : [ORIGIN];
      }
      if (!frame.data.tracking_valid) return previous.length ? previous : [ORIGIN];
      return [...(previous.length ? previous : [ORIGIN]), point].slice(
        -MAX_TRAIL_POINTS,
      );
    });
  }, [frame]);

  const current = frame
    ? { x: frame.data.position_x, y: frame.data.position_y }
    : trail[trail.length - 1] ?? ORIGIN;
  const points = trail.length ? trail : [ORIGIN];
  const mappedPoints = mapCoordinates([...points, current]);
  const plotted = mappedPoints.slice(0, points.length);
  const currentPosition = mappedPoints[mappedPoints.length - 1];
  const path = plotted.map(({ x, y }) => `${x},${y}`).join(' ');
  const status = !frame
    ? 'WAITING'
    : frame.data.tracking_valid
      ? 'FLOW LOCKED'
      : 'REACQUIRING';

  return (
    <section
      aria-label="Visual odometry minimap"
      className="fixed left-3 top-1/2 z-[2] w-44 -translate-y-1/2 hud-panel !p-3 pointer-events-none"
    >
      <h2 className="hud-label mb-2 text-white">Visual Odometry</h2>
      <svg
        role="img"
        aria-label="Relative image-space movement map"
        viewBox="0 0 100 100"
        className="w-full rounded border border-white/10 bg-black/40"
      >
        <path d="M50 8v84M8 50h84" stroke="white" strokeOpacity="0.14" />
        <circle cx="50" cy="50" r="2" fill="white" fillOpacity="0.45" />
        <polyline
          points={path}
          fill="none"
          stroke="#38bdf8"
          strokeWidth="1.5"
          strokeLinejoin="round"
          strokeLinecap="round"
        />
        <circle
          cx={currentPosition.x}
          cy={currentPosition.y}
          r="3"
          fill={frame?.data.tracking_valid ? '#a3e635' : '#fbbf24'}
          stroke="#111827"
          strokeWidth="1"
        />
      </svg>
      <div className="mt-2 flex items-center justify-between">
        <span className="hud-label">{status}</span>
        {frame && (
          <span className="font-mono text-[10px] text-white/60">
            {Math.round(frame.data.quality * 100)}%
          </span>
        )}
      </div>
      <div className="mt-1 font-mono text-[10px] text-white/70">
        X {current.x.toFixed(3)} / Y {current.y.toFixed(3)}
      </div>
      <p className="mt-1 text-[9px] leading-relaxed text-white/45">
        Relative image units, not meters or GPS.
      </p>
    </section>
  );
}
