import { act, renderHook } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { useWebSocket } from '@/hooks/useWebSocket';
import { useDroneStore } from '@/stores/droneStore';

class MockWebSocket {
  static latest: MockWebSocket;
  onopen: ((event: Event) => void) | null = null;
  onmessage: ((event: MessageEvent) => void) | null = null;
  onclose: ((event: CloseEvent) => void) | null = null;
  onerror: ((event: Event) => void) | null = null;
  close = vi.fn();

  constructor(_url: string) {
    MockWebSocket.latest = this;
  }
}

describe('useWebSocket vision messages', () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    useDroneStore.setState({
      connectionStatus: 'disconnected',
      previewMode: false,
      visionFrame: null,
    });
  });

  it('stores the latest timestamped vision result', () => {
    vi.stubGlobal('WebSocket', MockWebSocket);
    useDroneStore.setState({ connectionStatus: 'connected', previewMode: false });
    const { unmount } = renderHook(() => useWebSocket());
    const visionMessage = {
      type: 'vision',
      timestamp: '2026-11-15T00:00:00Z',
      data: {
        frame_id: 3,
        frame_width: 640,
        frame_height: 480,
        model: 'test-model',
        device: 'cpu',
        inference_ms: 10,
        detections: [
          {
            label: 'person',
            confidence: 0.9,
            x_min: 0.1,
            y_min: 0.2,
            x_max: 0.6,
            y_max: 0.8,
          },
        ],
      },
    };

    act(() => {
      MockWebSocket.latest.onmessage?.({
        data: JSON.stringify(visionMessage),
      } as MessageEvent);
    });

    expect(useDroneStore.getState().visionFrame).toEqual({
      data: visionMessage.data,
      timestamp: visionMessage.timestamp,
    });
    unmount();
  });
});
