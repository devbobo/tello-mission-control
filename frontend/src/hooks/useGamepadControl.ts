import { useEffect, useRef, useState } from 'react';
import { useDroneStore } from '@/stores/droneStore';
import * as api from '@/lib/api';

const POLL_INTERVAL_MS = 50;
const SEND_INTERVAL_MS = 100;
const DEADZONE = 0.15;

export interface RcVector {
  lr: number;
  fb: number;
  ud: number;
  yaw: number;
}

interface GamepadInfo {
  id: string;
  index: number;
  mapping: string;
  axisCount: number;
  buttonCount: number;
}

interface ControlState {
  enabled: boolean;
  connected: boolean;
  flying: boolean;
  commandPending: boolean;
  previewMode: boolean;
  sequenceRunning: boolean;
}

const ZERO_RC: RcVector = { lr: 0, fb: 0, ud: 0, yaw: 0 };

function isZero(vector: RcVector): boolean {
  return vector.lr === 0 && vector.fb === 0 && vector.ud === 0 && vector.yaw === 0;
}

function scaleAxis(value: number): number {
  if (!Number.isFinite(value)) return 0;
  const clamped = Math.max(-1, Math.min(1, value));
  const magnitude = Math.abs(clamped);
  if (magnitude <= DEADZONE) return 0;
  return Math.round(Math.sign(clamped) * ((magnitude - DEADZONE) / (1 - DEADZONE)) * 100);
}

function invertAxis(value: number): number {
  const scaled = scaleAxis(value);
  return scaled === 0 ? 0 : -scaled;
}

export function mapGamepadAxes(axes: readonly number[]): RcVector {
  return {
    lr: scaleAxis(axes[0] ?? 0),
    fb: invertAxis(axes[1] ?? 0),
    ud: invertAxis(axes[3] ?? 0),
    yaw: scaleAxis(axes[2] ?? 0),
  };
}

export function useGamepadControl() {
  const connectionStatus = useDroneStore((state) => state.connectionStatus);
  const isFlying = useDroneStore((state) => state.isFlying);
  const commandPending = useDroneStore((state) => state.commandPending);
  const previewMode = useDroneStore((state) => state.previewMode);
  const sequenceProgress = useDroneStore((state) => state.sequenceProgress);

  const [enabled, setEnabled] = useState(false);
  const [gamepad, setGamepad] = useState<GamepadInfo | null>(null);
  const [deadmanHeld, setDeadmanHeld] = useState(false);
  const [commandBusy, setCommandBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const supported = typeof navigator !== 'undefined' && typeof navigator.getGamepads === 'function';
  const stateRef = useRef<ControlState>({
    enabled: false,
    connected: false,
    flying: false,
    commandPending: false,
    previewMode: false,
    sequenceRunning: false,
  });
  stateRef.current = {
    enabled,
    connected: connectionStatus === 'connected',
    flying: isFlying,
    commandPending,
    previewMode,
    sequenceRunning: sequenceProgress?.status === 'running',
  };

  useEffect(() => {
    let disposed = false;
    let lastSent = ZERO_RC;
    let lastAttempted = ZERO_RC;
    let lastSentAt = 0;
    let pendingRequest: Promise<void> | null = null;

    const send = (vector: RcVector) => {
      if (pendingRequest) return;
      lastAttempted = vector;
      lastSentAt = Date.now();
      const request = api.sendRc(vector.lr, vector.fb, vector.ud, vector.yaw)
        .then((response) => {
          if (response.ok) {
            lastSent = vector;
            if (!disposed) {
              setCommandBusy(false);
              setError(null);
            }
          } else if (response.error?.includes('Another drone command is in progress')) {
            if (!disposed) setCommandBusy(true);
          } else {
            if (!disposed) {
              setError(response.error ?? 'Gamepad command failed');
              setEnabled(false);
            }
          }
        })
        .finally(() => {
          if (pendingRequest === request) pendingRequest = null;
        });
      pendingRequest = request;
    };

    const update = () => {
      const pads = supported ? Array.from(navigator.getGamepads()) : [];
      const pad = pads.find((candidate): candidate is Gamepad => Boolean(candidate?.connected)) ?? null;
      const padInfo = pad
        ? {
            id: pad.id,
            index: pad.index,
            mapping: pad.mapping,
            axisCount: pad.axes.length,
            buttonCount: pad.buttons.length,
          }
        : null;
      setGamepad((current) =>
        current?.id === padInfo?.id &&
        current?.index === padInfo?.index &&
        current?.mapping === padInfo?.mapping &&
        current?.axisCount === padInfo?.axisCount &&
        current?.buttonCount === padInfo?.buttonCount
          ? current
          : padInfo,
      );

      const state = stateRef.current;
      const gamepadReady = Boolean(
        pad?.mapping === 'standard' && pad.axes.length >= 4 && pad.buttons.length > 0,
      );
      if (state.enabled && !gamepadReady) {
        setEnabled(false);
      }
      if (
        state.enabled &&
        (!state.connected ||
          !state.flying ||
          state.commandPending ||
          state.previewMode ||
          state.sequenceRunning)
      ) {
        setEnabled(false);
      }

      const controlling = Boolean(
        state.enabled &&
        state.connected &&
        state.flying &&
        !state.commandPending &&
        !state.previewMode &&
        !state.sequenceRunning &&
        !document.hidden &&
        gamepadReady &&
        pad?.buttons[0]?.pressed,
      );
      setDeadmanHeld((current) => (current === controlling ? current : controlling));

      const vector = controlling && pad ? mapGamepadAxes(pad.axes) : ZERO_RC;
      const now = Date.now();
      if (!isZero(vector)) {
        if (now - lastSentAt >= SEND_INTERVAL_MS) send(vector);
      } else if (
        now - lastSentAt >= SEND_INTERVAL_MS &&
        (!isZero(lastSent) || !isZero(lastAttempted))
      ) {
        send(ZERO_RC);
      }
    };

    const handleVisibilityChange = () => {
      if (document.hidden && stateRef.current.enabled) setEnabled(false);
    };

    const interval = window.setInterval(update, POLL_INTERVAL_MS);
    document.addEventListener('visibilitychange', handleVisibilityChange);
    update();

    return () => {
      disposed = true;
      window.clearInterval(interval);
      document.removeEventListener('visibilitychange', handleVisibilityChange);
      if (!stateRef.current.connected || stateRef.current.previewMode) return;
      void (async () => {
        if (pendingRequest) await pendingRequest;
        if (isZero(lastSent) && isZero(lastAttempted)) return;
        const response = await api.sendRc(0, 0, 0, 0);
        if (!response.ok) {
          console.error('Failed to send neutral gamepad command during cleanup:', response.error);
        }
      })();
    };
  }, [supported]);

  const gamepadReady = Boolean(
    gamepad?.mapping === 'standard' && gamepad.axisCount >= 4 && gamepad.buttonCount > 0,
  );
  const canEnable = Boolean(
    supported &&
    gamepadReady &&
    isFlying &&
    connectionStatus === 'connected' &&
    !commandPending &&
    !previewMode &&
    sequenceProgress?.status !== 'running',
  );
  const status = error
    ? error
    : commandBusy
      ? 'Waiting for current flight command'
      : !supported
        ? 'Gamepad API unavailable in this browser'
        : !gamepad
          ? 'Connect a standard gamepad'
          : !gamepadReady
            ? 'Use a standard-mapped gamepad'
            : previewMode
              ? 'Unavailable in preview mode'
              : commandPending
                ? 'A flight command is in progress'
              : !isFlying
                ? 'Take off to enable gamepad'
                : enabled
                  ? deadmanHeld
                    ? 'Control active — release A/Cross to stop'
                    : 'Hold A/Cross to control'
                  : 'Enable, then hold A/Cross to control';

  return {
    enabled,
    canEnable: canEnable || enabled,
    deadmanHeld,
    status,
    toggle: () => {
      setError(null);
      setCommandBusy(false);
      setEnabled((current) => !current);
    },
  };
}
