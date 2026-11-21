import { act, renderHook, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { useWebSocket } from '@/hooks/useWebSocket';
import { useDroneStore } from '@/stores/droneStore';

class MockWebSocket {
  static OPEN = 1;
  static instances: MockWebSocket[] = [];

  readyState = 0;
  onopen: (() => void) | null = null;
  onmessage: ((event: { data: string }) => void) | null = null;
  onclose: (() => void) | null = null;
  onerror: (() => void) | null = null;
  sent: string[] = [];

  constructor(_url: string) {
    MockWebSocket.instances.push(this);
  }

  send(message: string) {
    this.sent.push(message);
  }

  close() {
    this.readyState = 3;
  }
}

describe('useWebSocket automatic recording protocol', () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    useDroneStore.setState({
      connectionStatus: 'disconnected',
      previewMode: false,
      recordingReady: false,
      recordingRequestHandler: null,
    });
    MockWebSocket.instances = [];
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
    act(() => socket.onopen?.());

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
      });
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
