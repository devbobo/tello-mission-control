import {
  ChevronUp,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  ArrowUp,
  ArrowDown,
  RotateCw,
  RotateCcw,
} from 'lucide-react';
import { useDroneStore } from '@/stores/droneStore';
import * as api from '@/lib/api';
import { getBatteryLevel } from '@/lib/format';
import type { FlipDirection, TelemetryData } from '@/types/drone';

const FLIP_LABELS: Record<FlipDirection, string> = {
  forward: 'FWD',
  back: 'BACK',
  left: 'LEFT',
  right: 'RIGHT',
};

interface ReplayControls {
  highlightedControls: string[];
  result: 'ok' | 'error' | null;
  params: Record<string, unknown>;
  telemetry: TelemetryData | null;
}

interface FlightControlsProps {
  replay?: ReplayControls;
}

export default function FlightControls({ replay }: FlightControlsProps) {
  const {
    isFlying,
    commandPending,
    moveDistance: configuredMoveDistance,
    rotateAngle: configuredRotateAngle,
    setMoveDistance,
    setRotateAngle,
    sendCommand,
    telemetry: liveTelemetry,
  } = useDroneStore();

  const telemetry = replay ? replay.telemetry : liveTelemetry;
  const moveDistance =
    typeof replay?.params.distance_cm === 'number'
      ? replay.params.distance_cm
      : configuredMoveDistance;
  const rotateAngle =
    typeof replay?.params.angle_deg === 'number'
      ? replay.params.angle_deg
      : configuredRotateAngle;
  const disabled = replay !== undefined || !isFlying || commandPending;
  const lowBattery = getBatteryLevel(telemetry?.battery ?? 100) !== 'ok';
  const isHighlighted = (control: string) => replay?.highlightedControls.includes(control) ?? false;
  const highlightClass = (control: string) => {
    if (!isHighlighted(control)) return '';
    return replay?.result === 'error'
      ? '!border-danger !text-danger !opacity-100 ring-2 ring-danger/80 shadow-[0_0_14px_rgba(255,59,48,0.4)]'
      : '!border-info !text-info !opacity-100 ring-2 ring-info/80 shadow-[0_0_14px_rgba(0,212,255,0.4)]';
  };

  return (
    <div className="hud-panel animate-fade-in-up max-w-[320px] !p-3">
      <h3 className="hud-label mb-2">Flight Controls</h3>

      {/* D-Pad */}
      <div className="grid grid-cols-3 gap-2 justify-items-center">
        <div />
        <button
          className={`control-btn w-10 h-10 relative ${highlightClass('move_forward')}`}
          disabled={disabled}
          data-replay-active={isHighlighted('move_forward') || undefined}
          onClick={() => sendCommand(() => api.move('forward', moveDistance))}
          aria-label="Move forward"
        >
          <ChevronUp size={20} />
          <span className="absolute bottom-0.5 right-1 text-[9px] text-white/30">W</span>
        </button>
        <div />

        <button
          className={`control-btn w-10 h-10 relative ${highlightClass('move_left')}`}
          disabled={disabled}
          data-replay-active={isHighlighted('move_left') || undefined}
          onClick={() => sendCommand(() => api.move('left', moveDistance))}
          aria-label="Move left"
        >
          <ChevronLeft size={20} />
          <span className="absolute bottom-0.5 right-1 text-[9px] text-white/30">A</span>
        </button>
        <div className="flex items-center justify-center">
          <span className="block w-2 h-2 rounded-full bg-white/30" />
        </div>
        <button
          className={`control-btn w-10 h-10 relative ${highlightClass('move_right')}`}
          disabled={disabled}
          data-replay-active={isHighlighted('move_right') || undefined}
          onClick={() => sendCommand(() => api.move('right', moveDistance))}
          aria-label="Move right"
        >
          <ChevronRight size={20} />
          <span className="absolute bottom-0.5 right-1 text-[9px] text-white/30">D</span>
        </button>

        <div />
        <button
          className={`control-btn w-10 h-10 relative ${highlightClass('move_back')}`}
          disabled={disabled}
          data-replay-active={isHighlighted('move_back') || undefined}
          onClick={() => sendCommand(() => api.move('back', moveDistance))}
          aria-label="Move back"
        >
          <ChevronDown size={20} />
          <span className="absolute bottom-0.5 right-1 text-[9px] text-white/30">S</span>
        </button>
        <div />
      </div>

      {/* Vertical Controls */}
      <div className="flex gap-2 mt-3">
        <button
          className={`control-btn flex-1 h-10 relative ${highlightClass('move_up')}`}
          disabled={disabled}
          data-replay-active={isHighlighted('move_up') || undefined}
          onClick={() => sendCommand(() => api.move('up', moveDistance))}
          aria-label="Move up"
        >
          <ArrowUp size={18} />
          UP
          <span className="absolute bottom-0.5 right-1.5 text-[9px] text-white/30 normal-case">Space</span>
        </button>
        <button
          className={`control-btn flex-1 h-10 relative ${highlightClass('move_down')}`}
          disabled={disabled}
          data-replay-active={isHighlighted('move_down') || undefined}
          onClick={() => sendCommand(() => api.move('down', moveDistance))}
          aria-label="Move down"
        >
          <ArrowDown size={18} />
          DOWN
          <span className="absolute bottom-0.5 right-1.5 text-[9px] text-white/30 normal-case">Shift</span>
        </button>
      </div>

      {/* Rotation Controls */}
      <div className="mt-3">
        <span className="hud-label block mb-1.5">Rotation</span>
        <div className="flex gap-2">
          <button
            className={`control-btn flex-1 h-10 relative ${highlightClass('rotate_ccw')}`}
            disabled={disabled}
            data-replay-active={isHighlighted('rotate_ccw') || undefined}
            onClick={() => sendCommand(() => api.rotate('ccw', rotateAngle))}
            aria-label="Rotate counter-clockwise"
          >
            <RotateCcw size={18} />
            CCW
            <span className="absolute bottom-0.5 right-1.5 text-[9px] text-white/30">Q</span>
          </button>
          <button
            className={`control-btn flex-1 h-10 relative ${highlightClass('rotate_cw')}`}
            disabled={disabled}
            data-replay-active={isHighlighted('rotate_cw') || undefined}
            onClick={() => sendCommand(() => api.rotate('cw', rotateAngle))}
            aria-label="Rotate clockwise"
          >
            <RotateCw size={18} />
            CW
            <span className="absolute bottom-0.5 right-1.5 text-[9px] text-white/30">E</span>
          </button>
        </div>
      </div>

      {/* Flip Controls */}
      <div className="mt-3">
        <span className="hud-label block mb-1.5">Flips</span>
        <div className="flex gap-1.5">
          {(['forward', 'back', 'left', 'right'] as FlipDirection[]).map((dir) => (
            <button
              key={dir}
              className={`control-btn flex-1 text-hud-xs px-1.5 py-2 ${
                lowBattery ? 'opacity-50' : ''
              } ${highlightClass(`flip_${dir}`)}`}
              disabled={disabled}
              data-replay-active={isHighlighted(`flip_${dir}`) || undefined}
              title={lowBattery ? 'Low battery — flips may fail below 50%' : `Flip ${dir}`}
              onClick={() => sendCommand(() => api.flip(dir))}
            >
              {FLIP_LABELS[dir]}
            </button>
          ))}
        </div>
      </div>

      {/* Distance Slider */}
      <div className="mt-3">
        <div className="flex items-center justify-between mb-1">
          <span className="hud-label">Distance</span>
          <span className="font-mono text-hud-xs">{moveDistance} cm</span>
        </div>
        <input
          type="range"
          className="hud-slider"
          disabled={replay !== undefined}
          min={20}
          max={500}
          step={10}
          value={moveDistance}
          onChange={(e) => setMoveDistance(Number(e.target.value))}
        />
      </div>

      {/* Angle Slider */}
      <div className="mt-2">
        <div className="flex items-center justify-between mb-1">
          <span className="hud-label">Angle</span>
          <span className="font-mono text-hud-xs">{rotateAngle}&deg;</span>
        </div>
        <input
          type="range"
          className="hud-slider"
          disabled={replay !== undefined}
          min={1}
          max={360}
          step={1}
          value={rotateAngle}
          onChange={(e) => setRotateAngle(Number(e.target.value))}
        />
      </div>
    </div>
  );
}
