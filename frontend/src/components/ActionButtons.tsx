import { useState } from 'react';
import { Gamepad2, Plane, Play } from 'lucide-react';
import { useDroneStore } from '@/stores/droneStore';
import * as api from '@/lib/api';
import { useGamepadControl } from '@/hooks/useGamepadControl';

interface ActionButtonsProps {
  onOpenSequences?: () => void;
}

export default function ActionButtons({ onOpenSequences }: ActionButtonsProps) {
  const {
    isFlying,
    commandPending,
    connectionStatus,
    sequenceProgress,
    sendCommand,
    setIsFlying,
  } = useDroneStore();

  const [sequenceModalOpen, setSequenceModalOpen] = useState(false);
  const gamepad = useGamepadControl();

  const isRunning = sequenceProgress?.status === 'running';

  const handleOpenSequences = () => {
    if (onOpenSequences) {
      onOpenSequences();
    } else {
      setSequenceModalOpen(!sequenceModalOpen);
    }
  };

  // Sequence running state — replace action buttons with progress view
  if (isRunning && sequenceProgress) {
    const progress = (sequenceProgress.current_step / sequenceProgress.total_steps) * 100;

    return (
      <div className="animate-fade-in-up hud-panel space-y-3">
        <span className="text-hud-sm font-medium uppercase tracking-wider">
          {sequenceProgress.sequence_id}
        </span>

        {/* Progress bar */}
        <div className="h-1 w-full rounded-full bg-white/10 overflow-hidden">
          <div
            className="h-full bg-info rounded-full transition-all duration-300"
            style={{ width: `${progress}%` }}
          />
        </div>

        <span className="text-hud-xs text-hud-secondary block">
          Step {sequenceProgress.current_step}/{sequenceProgress.total_steps}
          {sequenceProgress.step_description ? ` — ${sequenceProgress.step_description}` : ''}
        </span>

        <button
          className="control-btn border-caution text-caution hover:bg-caution/20 w-full px-4 py-2"
          onClick={() => api.cancelSequence()}
        >
          Abort
        </button>
      </div>
    );
  }

  return (
    <div className="hud-panel animate-fade-in-up flex flex-wrap items-center gap-2 sm:gap-3">
      {/* Takeoff — primary action, slightly larger */}
      <button
        className="control-btn border-ok text-ok hover:bg-ok/20 px-4 py-2.5 sm:px-6 sm:py-3.5 shadow-[0_0_12px_rgba(0,212,106,0.15)]"
        disabled={isFlying || commandPending || connectionStatus !== 'connected'}
        onClick={async () => {
          const ok = await sendCommand(() => api.takeoff());
          if (ok) setIsFlying(true);
        }}
        aria-label="Takeoff (T)"
      >
        <Plane size={18} />
        Takeoff
        <span className="text-[9px] text-ok/40 ml-1 normal-case">T</span>
      </button>

      {/* Land */}
      <button
        className="control-btn border-info text-info hover:bg-info/20 px-3 py-2.5 sm:px-5 sm:py-3"
        disabled={!isFlying || commandPending}
        onClick={async () => {
          const ok = await sendCommand(() => api.land());
          if (ok) setIsFlying(false);
        }}
        aria-label="Land (L)"
      >
        Land
        <span className="text-[9px] text-info/40 ml-1 normal-case">L</span>
      </button>

      {/* Sequences */}
      <button
        className="control-btn border-hud-secondary/30 text-hud-secondary px-3 py-2.5 sm:px-4 sm:py-3"
        disabled={!isFlying || isRunning || gamepad.enabled}
        onClick={handleOpenSequences}
      >
        <Play size={18} />
        Sequences
      </button>

      <div className="flex flex-col items-center">
        <button
          className={`control-btn px-2.5 py-2.5 sm:px-3 ${
            gamepad.enabled ? 'border-info text-info' : 'text-hud-secondary'
          }`}
          disabled={!gamepad.canEnable}
          onClick={gamepad.toggle}
          aria-label={gamepad.enabled ? 'Disable gamepad control' : 'Enable gamepad control'}
          title={gamepad.status}
        >
          <Gamepad2 size={18} />
          <span className="hidden sm:inline">Gamepad</span>
          <span
            className={`h-1.5 w-1.5 rounded-full ${
              gamepad.deadmanHeld ? 'bg-ok' : gamepad.enabled ? 'bg-caution' : 'bg-hud-dim'
            }`}
          />
        </button>
        {gamepad.enabled && (
          <span className="mt-1 max-w-[120px] text-center text-[9px] leading-tight text-hud-secondary">
            {gamepad.deadmanHeld ? 'RC active — release A/Cross to stop' : 'Hold A/Cross to fly'}
          </span>
        )}
        <span className="sr-only" aria-live="polite">{gamepad.status}</span>
      </div>
    </div>
  );
}
