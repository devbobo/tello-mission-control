import { useFreshVisionFrame } from '@/hooks/useFreshVisionFrame';

interface VisionOverlayProps {
  selectedTrackId?: number | null;
}

export default function VisionOverlay({
  selectedTrackId = null,
}: VisionOverlayProps) {
  const visionFrame = useFreshVisionFrame();
  if (!visionFrame) return null;

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
        const isSelected = detection.track_id === selectedTrackId;

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
              stroke={isSelected ? '#38bdf8' : '#a3e635'}
              strokeWidth={isSelected ? '3' : '2'}
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
