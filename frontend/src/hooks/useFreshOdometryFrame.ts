import { useEffect, useState } from 'react';
import { useDroneStore } from '@/stores/droneStore';
import type { OdometryFrame } from '@/types/drone';

const ODOMETRY_MAX_AGE_MS = 1500;

export function useFreshOdometryFrame(): OdometryFrame | null {
  const odometryFrame = useDroneStore((s) => s.odometryFrame);
  const [expiredFrame, setExpiredFrame] = useState<OdometryFrame | null>(null);

  useEffect(() => {
    if (!odometryFrame) return;

    const expiresIn =
      Date.parse(odometryFrame.timestamp) + ODOMETRY_MAX_AGE_MS - Date.now();
    if (!Number.isFinite(expiresIn) || expiresIn <= 0) return;

    const timeout = window.setTimeout(
      () => setExpiredFrame(odometryFrame),
      expiresIn,
    );
    return () => window.clearTimeout(timeout);
  }, [odometryFrame]);

  if (!odometryFrame || odometryFrame === expiredFrame) return null;

  const expiresIn =
    Date.parse(odometryFrame.timestamp) + ODOMETRY_MAX_AGE_MS - Date.now();
  return Number.isFinite(expiresIn) && expiresIn > 0 ? odometryFrame : null;
}
