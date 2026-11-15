import { useCallback } from 'react';
import { AlertOctagon } from 'lucide-react';
import * as api from '@/lib/api';
import { useDroneStore } from '@/stores/droneStore';

export default function EmergencyButton() {
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
        className="emergency-btn"
        onClick={handleEmergency}
        tabIndex={1}
        aria-label="Emergency Stop"
      >
        <AlertOctagon size={20} />
        EMERGENCY STOP
      </button>
    </div>
  );
}
