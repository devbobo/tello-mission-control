import { useEffect, useState } from 'react';
import { useDroneStore } from '@/stores/droneStore';
import type { MarkerFrame } from '@/types/drone';

const MARKER_RESULT_MAX_AGE_MS = 1500;

export function useFreshMarkerFrame(): MarkerFrame | null {
  const markerFrame = useDroneStore((s) => s.markerFrame);
  const [expiredFrame, setExpiredFrame] = useState<MarkerFrame | null>(null);

  useEffect(() => {
    if (!markerFrame) return;

    const expiresIn =
      Date.parse(markerFrame.timestamp) + MARKER_RESULT_MAX_AGE_MS - Date.now();
    if (!Number.isFinite(expiresIn) || expiresIn <= 0) return;

    const timeout = window.setTimeout(
      () => setExpiredFrame(markerFrame),
      expiresIn,
    );
    return () => window.clearTimeout(timeout);
  }, [markerFrame]);

  if (!markerFrame || markerFrame === expiredFrame) return null;

  const expiresIn =
    Date.parse(markerFrame.timestamp) + MARKER_RESULT_MAX_AGE_MS - Date.now();
  return Number.isFinite(expiresIn) && expiresIn > 0 ? markerFrame : null;
}
