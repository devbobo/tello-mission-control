import { useEffect, useState } from 'react';
import { useDroneStore } from '@/stores/droneStore';
import type { VisionFrame } from '@/types/drone';

const RESULT_MAX_AGE_MS = 1500;

export default function VisionOverlay() {
  const visionFrame = useDroneStore((s) => s.visionFrame);
  const [expiredFrame, setExpiredFrame] = useState<VisionFrame | null>(null);

  useEffect(() => {
    if (!visionFrame) return;

    const expiresIn =
      Date.parse(visionFrame.timestamp) + RESULT_MAX_AGE_MS - Date.now();
    if (!Number.isFinite(expiresIn) || expiresIn <= 0) return;

    const timeout = window.setTimeout(
      () => setExpiredFrame(visionFrame),
      expiresIn,
    );
    return () => window.clearTimeout(timeout);
  }, [visionFrame]);

  if (!visionFrame || visionFrame === expiredFrame) return null;

  const expiresIn =
    Date.parse(visionFrame.timestamp) + RESULT_MAX_AGE_MS - Date.now();
  if (!Number.isFinite(expiresIn) || expiresIn <= 0) return null;

  const { frame_width: frameWidth, frame_height: frameHeight, detections } =
    visionFrame.data;

  return (
    <svg
      data-testid="vision-overlay"
      aria-label="Object detection overlay"
      role="img"
      className="fixed inset-0 z-[1] h-full w-full pointer-events-none"
      viewBox={`0 0 ${frameWidth} ${frameHeight}`}
      preserveAspectRatio="xMidYMid slice"
    >
      <title>Object detection overlay</title>
      {detections.map((detection, index) => {
        const x = detection.x_min * frameWidth;
        const y = detection.y_min * frameHeight;
        const width = (detection.x_max - detection.x_min) * frameWidth;
        const height = (detection.y_max - detection.y_min) * frameHeight;
        const labelY = Math.max(y - 6, 12);

        return (
          <g
            key={`${visionFrame.data.frame_id}-${index}`}
            aria-label={`${detection.label}, ${Math.round(detection.confidence * 100)}% confidence`}
          >
            <rect
              x={x}
              y={y}
              width={width}
              height={height}
              rx="2"
              fill="none"
              stroke="#a3e635"
              strokeWidth="2"
              vectorEffect="non-scaling-stroke"
            />
            <text
              x={x}
              y={labelY}
              fill="white"
              fontSize="10"
              fontWeight="700"
              paintOrder="stroke"
              stroke="#111827"
              strokeLinejoin="round"
              strokeWidth="3"
            >
              {detection.label} {Math.round(detection.confidence * 100)}%
            </text>
          </g>
        );
      })}
    </svg>
  );
}
