import { useCallback } from 'react';
import { AlertOctagon } from 'lucide-react';
import * as api from '@/lib/api';
import { useDroneStore } from '@/stores/droneStore';

interface EmergencyButtonProps {
  replay?: { highlighted: boolean };
}

export default function EmergencyButton({ replay }: EmergencyButtonProps) {
  const setIsFlying = useDroneStore((state) => state.setIsFlying);

  const handleEmergency = useCallback(() => {
    void api.emergencyStop().then((response) => {
      if (response.ok) setIsFlying(false);
    });
  }, [setIsFlying]);

  return (
    <div className="fixed bottom-3 right-3 sm:bottom-6 sm:right-6 z-[3]">
      <button
        type="button"
        className={`emergency-btn ${replay ? 'pointer-events-none !animate-none' : ''} ${
          replay?.highlighted
            ? '!opacity-100 ring-2 ring-danger shadow-[0_0_16px_rgba(255,59,48,0.65)]'
            : replay ? 'opacity-25' : ''
        }`}
        disabled={replay !== undefined}
        data-replay-active={replay?.highlighted || undefined}
        onClick={replay ? undefined : handleEmergency}
        tabIndex={1}
        aria-label="Emergency Stop"
        title={replay ? 'Historical emergency event' : undefined}
      >
        <AlertOctagon size={20} />
        EMERGENCY STOP
      </button>
    </div>
  );
}
