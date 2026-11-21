import { useId } from 'react';
import type { TelemetryData } from '@/types/drone';

interface ArtificialHorizonProps {
  attitude: TelemetryData['attitude'] | null;
  className?: string;
}

export default function ArtificialHorizon({
  attitude,
  className = 'h-20 w-20',
}: ArtificialHorizonProps) {
  const clipId = useId();
  const skyId = useId();
  const groundId = useId();
  const available = attitude !== null &&
    Number.isFinite(attitude.pitch) &&
    Number.isFinite(attitude.roll);
  const pitch = available ? attitude.pitch : 0;
  const roll = available ? attitude.roll : 0;
  const pitchOffset = Math.max(-90, Math.min(90, pitch)) * 11 / 10;

  return (
    <svg
      className={`shrink-0 ${className}`}
      viewBox="0 0 120 120"
      role="img"
      aria-label={available
        ? `Artificial horizon: pitch ${pitch} degrees, roll ${roll} degrees`
        : 'Artificial horizon: attitude unavailable'}
    >
      <defs>
        <clipPath id={clipId}>
          <circle cx="60" cy="60" r="52" />
        </clipPath>
        <linearGradient id={skyId} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor="#154467" />
          <stop offset="1" stopColor="#2785c0" />
        </linearGradient>
        <linearGradient id={groundId} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor="#8a6135" />
          <stop offset="1" stopColor="#342619" />
        </linearGradient>
      </defs>
      <circle cx="60" cy="60" r="59" fill="#111922" />
      <g transform="translate(60 60) scale(1.125) translate(-60 -60)">
        {available ? (
          <>
            <g clipPath={`url(#${clipId})`}>
              <g
                data-testid="horizon-attitude"
                transform={`translate(60 ${60 + pitchOffset})`}
              >
                <rect x="-300" y="-300" width="600" height="300" fill={`url(#${skyId})`} />
                <rect x="-300" y="0" width="600" height="300" fill={`url(#${groundId})`} />
                <path d="M-300 0H300" stroke="#f1f5f6" strokeWidth="1.5" />
                {[-30, -20, -10, 10, 20, 30].map((degrees) => (
                  <g key={degrees} transform={`translate(0 ${degrees * 1.1})`}>
                    <path d="M-10 0H10" stroke="#e8eef0" strokeWidth="1" />
                    <text x="-13" y="2" textAnchor="end" fill="#e8eef0" fontSize="5.5">
                      {Math.abs(degrees)}
                    </text>
                    <text x="13" y="2" fill="#e8eef0" fontSize="5.5">
                      {Math.abs(degrees)}
                    </text>
                  </g>
                ))}
              </g>
            </g>
            <g
              data-testid="horizon-bank-scale"
              transform={`rotate(${roll} 60 60)`}
              aria-hidden="true"
              stroke="#f0f3f4"
              strokeLinecap="round"
            >
              {[-60, -45, -30, -20, -10, 0, 10, 20, 30, 45, 60].map((degrees) => (
                <path
                  key={degrees}
                  transform={`rotate(${degrees} 60 60)`}
                  d={degrees % 30 === 0 ? 'M60 10V18' : 'M60 10V15'}
                  strokeWidth={degrees === 0 ? 2 : 1.5}
                />
              ))}
            </g>
            <g data-testid="horizon-aircraft" transform={`rotate(${roll} 60 60)`}>
              <path
                d="M24 60H47L50 64M96 60H73L70 64M57 60H63"
                fill="none"
                stroke="#ffb02e"
                strokeWidth="3"
                strokeLinecap="round"
                strokeLinejoin="round"
              />
            </g>
            <path data-testid="horizon-bank-pointer" d="M56 22L60 15L64 22Z" fill="#ffb02e" />
          </>
        ) : (
          <text x="60" y="64" textAnchor="middle" fill="#a2aab2" fontSize="12">
            N/A
          </text>
        )}
      </g>
      <circle cx="60" cy="60" r="59" fill="none" stroke="#667483" strokeWidth="1.5" />
    </svg>
  );
}
