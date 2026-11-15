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
      odometryFrame: null,
      markerFrame: null,
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

  it('stores the latest timestamped odometry estimate', () => {
    vi.stubGlobal('WebSocket', MockWebSocket);
    useDroneStore.setState({ connectionStatus: 'connected', previewMode: false });
    const { unmount } = renderHook(() => useWebSocket());
    const odometryMessage = {
      type: 'odometry',
      timestamp: '2026-11-15T00:00:00Z',
      data: {
        frame_id: 3,
        frame_width: 640,
        frame_height: 480,
        position_x: 0.02,
        position_y: -0.01,
        delta_x: 0.01,
        delta_y: -0.005,
        tracking_valid: true,
        tracked_points: 14,
        quality: 0.8,
      },
    };

    act(() => {
      MockWebSocket.latest.onmessage?.({
        data: JSON.stringify(odometryMessage),
      } as MessageEvent);
    });

    expect(useDroneStore.getState().odometryFrame).toEqual({
      data: odometryMessage.data,
      timestamp: odometryMessage.timestamp,
    });
    unmount();
  });

  it('stores the latest timestamped marker detections', () => {
    vi.stubGlobal('WebSocket', MockWebSocket);
    useDroneStore.setState({ connectionStatus: 'connected', previewMode: false });
    const { unmount } = renderHook(() => useWebSocket());
    const markerMessage = {
      type: 'markers',
      timestamp: '2026-11-15T00:00:00Z',
      data: {
        frame_id: 4,
        frame_width: 640,
        frame_height: 480,
        inference_ms: 8,
        aruco_dictionary: 'DICT_4X4_50',
        markers: [
          {
            marker_type: 'aruco',
            marker_id: '7',
            payload: null,
            payload_truncated: false,
            x_min: 0.2,
            y_min: 0.3,
            x_max: 0.6,
            y_max: 0.7,
          },
        ],
      },
    };

    act(() => {
      MockWebSocket.latest.onmessage?.({
        data: JSON.stringify(markerMessage),
      } as MessageEvent);
    });

    expect(useDroneStore.getState().markerFrame).toEqual({
      data: markerMessage.data,
      timestamp: markerMessage.timestamp,
    });
    unmount();
  });
});
