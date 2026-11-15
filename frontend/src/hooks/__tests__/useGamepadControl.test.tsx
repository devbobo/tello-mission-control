import { act, renderHook, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import * as api from '@/lib/api';
import { useGamepadControl, mapGamepadAxes } from '@/hooks/useGamepadControl';
import { useDroneStore } from '@/stores/droneStore';

function createGamepad() {
  const buttons = Array.from({ length: 16 }, () => ({
    pressed: false,
    touched: false,
    value: 0,
  }));
  return {
    id: 'Test Standard Gamepad',
    index: 0,
    mapping: 'standard',
    connected: true,
    axes: [0, 0, 0, 0],
    buttons,
  };
}

describe('mapGamepadAxes', () => {
  it('maps standard stick axes, inverts forward and vertical directions, and applies a dead zone', () => {
    expect(mapGamepadAxes([0.1, -1, 0.5, -0.5])).toEqual({
      lr: 0,
      fb: 100,
      ud: 41,
      yaw: 41,
    });
  });

  it('clamps axes and treats missing or non-finite axes as neutral', () => {
    expect(mapGamepadAxes([2, Number.NaN])).toEqual({
      lr: 100,
      fb: 0,
      ud: 0,
      yaw: 0,
    });
  });
});

describe('useGamepadControl', () => {
  const originalGetGamepads = Object.getOwnPropertyDescriptor(navigator, 'getGamepads');

  afterEach(() => {
    vi.restoreAllMocks();
    if (originalGetGamepads) {
      Object.defineProperty(navigator, 'getGamepads', originalGetGamepads);
    } else {
      Reflect.deleteProperty(navigator, 'getGamepads');
    }
  });

  it('requires the dead-man button and sends neutral input when the controller disconnects', async () => {
    const pad = createGamepad();
    Object.defineProperty(navigator, 'getGamepads', {
      configurable: true,
      value: () => [pad],
    });
    const sendRc = vi.spyOn(api, 'sendRc').mockResolvedValue({ ok: true });
    useDroneStore.setState({
      connectionStatus: 'connected',
      isFlying: true,
      commandPending: false,
      previewMode: false,
      sequenceProgress: null,
    });

    const { result, unmount } = renderHook(() => useGamepadControl());
    await waitFor(() => expect(result.current.canEnable).toBe(true));
    act(() => result.current.toggle());
    pad.axes[0] = 1;
    pad.buttons[0].pressed = true;

    await waitFor(() => expect(sendRc).toHaveBeenCalledWith(100, 0, 0, 0));
    pad.connected = false;
    await waitFor(() => expect(sendRc).toHaveBeenCalledWith(0, 0, 0, 0));
    expect(result.current.enabled).toBe(false);
    unmount();
  });

  it('disarms when a discrete flight command starts', async () => {
    const pad = createGamepad();
    Object.defineProperty(navigator, 'getGamepads', {
      configurable: true,
      value: () => [pad],
    });
    const sendRc = vi.spyOn(api, 'sendRc').mockResolvedValue({ ok: true });
    useDroneStore.setState({
      connectionStatus: 'connected',
      isFlying: true,
      commandPending: false,
      previewMode: false,
      sequenceProgress: null,
    });

    const { result, unmount } = renderHook(() => useGamepadControl());
    await waitFor(() => expect(result.current.canEnable).toBe(true));
    act(() => result.current.toggle());
    pad.axes[0] = 1;
    pad.buttons[0].pressed = true;
    await waitFor(() => expect(sendRc).toHaveBeenCalledWith(100, 0, 0, 0));

    act(() => useDroneStore.setState({ commandPending: true }));
    await waitFor(() => expect(result.current.enabled).toBe(false));
    await waitFor(() => expect(sendRc).toHaveBeenCalledWith(0, 0, 0, 0));
    unmount();
  });
});
