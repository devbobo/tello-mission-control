import { useEffect, useState } from 'react';
import { useDroneStore } from '@/stores/droneStore';
import type { VisionFrame } from '@/types/drone';

export const VISION_RESULT_MAX_AGE_MS = 1500;

export function useFreshVisionFrame(): VisionFrame | null {
  const visionFrame = useDroneStore((s) => s.visionFrame);
  const [expiredFrame, setExpiredFrame] = useState<VisionFrame | null>(null);

  useEffect(() => {
    if (!visionFrame) return;

    const expiresIn =
      Date.parse(visionFrame.timestamp) +
      VISION_RESULT_MAX_AGE_MS -
      Date.now();
    if (!Number.isFinite(expiresIn) || expiresIn <= 0) return;

    const timeout = window.setTimeout(
      () => setExpiredFrame(visionFrame),
      expiresIn,
    );
    return () => window.clearTimeout(timeout);
  }, [visionFrame]);

  if (!visionFrame || visionFrame === expiredFrame) return null;

  const expiresIn =
    Date.parse(visionFrame.timestamp) +
    VISION_RESULT_MAX_AGE_MS -
    Date.now();
  return Number.isFinite(expiresIn) && expiresIn > 0 ? visionFrame : null;
}
