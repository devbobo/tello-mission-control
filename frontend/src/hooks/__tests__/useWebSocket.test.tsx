import { act, renderHook, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { useWebSocket } from '@/hooks/useWebSocket';
import { useDroneStore } from '@/stores/droneStore';

class MockWebSocket {
  static OPEN = 1;
  static latest: MockWebSocket | undefined;
  static instances: MockWebSocket[] = [];

  readyState = 0;
  onopen: ((event: Event) => void) | null = null;
  onmessage: ((event: MessageEvent) => void) | null = null;
  onclose: ((event: CloseEvent) => void) | null = null;
  onerror: ((event: Event) => void) | null = null;
  sent: string[] = [];

  constructor(_url: string) {
    MockWebSocket.latest = this;
    MockWebSocket.instances.push(this);
  }

  send = vi.fn((message: string) => {
    this.sent.push(message);
  });

  close = vi.fn(() => {
    this.readyState = 3;
  });
}

describe('useWebSocket messages', () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    useDroneStore.setState({
      connectionStatus: 'disconnected',
      previewMode: false,
      visionFrame: null,
      odometryFrame: null,
      markerFrame: null,
      recordingReady: false,
      recordingRequestHandler: null,
    });
    MockWebSocket.instances = [];
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
      MockWebSocket.latest?.onmessage?.({
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
      MockWebSocket.latest?.onmessage?.({
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
      MockWebSocket.latest?.onmessage?.({
        data: JSON.stringify(markerMessage),
      } as MessageEvent);
    });

    expect(useDroneStore.getState().markerFrame).toEqual({
      data: markerMessage.data,
      timestamp: markerMessage.timestamp,
    });
    unmount();
  });

  it('reports recorder readiness and acknowledges backend recording requests', async () => {
    vi.stubGlobal('WebSocket', MockWebSocket);
    const handler = vi.fn(async () => undefined);
    useDroneStore.setState({
      connectionStatus: 'connected',
      recordingReady: true,
      recordingRequestHandler: handler,
    });

    const { unmount } = renderHook(() => useWebSocket());
    await waitFor(() => expect(MockWebSocket.instances).toHaveLength(1));
    const socket = MockWebSocket.instances[0];
    socket.readyState = MockWebSocket.OPEN;
    act(() => socket.onopen?.(new Event('open')));

    expect(JSON.parse(socket.sent[0])).toEqual({
      type: 'recorder_status',
      data: { ready: true },
    });

    act(() => {
      socket.onmessage?.({
        data: JSON.stringify({
          type: 'recording_request',
          data: { request_id: 'request-1', action: 'start' },
        }),
      } as MessageEvent);
    });
    await waitFor(() => expect(handler).toHaveBeenCalledWith('start'));
    await waitFor(() => {
      expect(socket.sent.map((message) => JSON.parse(message))).toContainEqual({
        type: 'recording_ack',
        data: { request_id: 'request-1', ok: true },
      });
    });

    act(() => useDroneStore.setState({ recordingReady: false }));
    expect(JSON.parse(socket.sent[socket.sent.length - 1] ?? '')).toEqual({
      type: 'recorder_status',
      data: { ready: false },
    });
    unmount();
  });
});
