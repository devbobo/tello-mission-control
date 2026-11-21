import { useEffect, useRef } from 'react';
import { useDroneStore } from '@/stores/droneStore';
import type { WsMessage } from '@/types/drone';

const MAX_BACKOFF = 16000;

async function handleRecordingRequest(
  ws: WebSocket,
  request: Extract<WsMessage, { type: 'recording_request' }>['data'],
) {
  const handler = useDroneStore.getState().recordingRequestHandler;
  let acknowledgement: { type: 'recording_ack'; data: { request_id: string; ok: boolean; error?: string } };
  try {
    if (!handler) throw new Error('The browser video recorder is unavailable');
    await handler(request.action);
    acknowledgement = {
      type: 'recording_ack',
      data: { request_id: request.request_id, ok: true },
    };
  } catch (error) {
    acknowledgement = {
      type: 'recording_ack',
      data: {
        request_id: request.request_id,
        ok: false,
        error: error instanceof Error ? error.message : 'Browser recording failed',
      },
    };
  }
  if (ws.readyState === WebSocket.OPEN) {
    ws.send(JSON.stringify(acknowledgement));
  }
}

export function useWebSocket() {
  const connectionStatus = useDroneStore((s) => s.connectionStatus);
  const previewMode = useDroneStore((s) => s.previewMode);
  const setTelemetry = useDroneStore((s) => s.setTelemetry);
  const addCommandLog = useDroneStore((s) => s.addCommandLog);
  const setSequenceProgress = useDroneStore((s) => s.setSequenceProgress);
  const setIsFlying = useDroneStore((s) => s.setIsFlying);

  const wsRef = useRef<WebSocket | null>(null);
  const backoffRef = useRef(1000);
  const reconnectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    // Don't connect WebSocket in preview mode — no backend available
    if (connectionStatus !== 'connected' || previewMode) {
      // Clean up on disconnect
      if (wsRef.current) {
        wsRef.current.close();
        wsRef.current = null;
      }
      if (reconnectTimerRef.current) {
        clearTimeout(reconnectTimerRef.current);
        reconnectTimerRef.current = null;
      }
      return;
    }

    function connect() {
      const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
      const ws = new WebSocket(`${protocol}//${window.location.host}/api/ws/telemetry`);
      wsRef.current = ws;

      ws.onopen = () => {
        backoffRef.current = 1000; // Reset backoff on success
        ws.send(JSON.stringify({
          type: 'recorder_status',
          data: { ready: useDroneStore.getState().recordingReady },
        }));
      };

      ws.onmessage = (event) => {
        try {
          const msg: WsMessage = JSON.parse(event.data);

          switch (msg.type) {
            case 'telemetry': {
              const data = msg.data;
              setTelemetry(data);
              // Infer flying state from height
              if (data.height > 0) {
                setIsFlying(true);
              }
              break;
            }
            case 'command_log':
              addCommandLog(msg.data);
              break;
            case 'sequence_progress': {
              const progress = msg.data;
              if (progress.status === 'completed' || progress.status === 'cancelled' || progress.status === 'error') {
                // Clear progress after a brief delay so user sees final state
                setSequenceProgress(progress);
                setTimeout(() => setSequenceProgress(null), 2000);
              } else {
                setSequenceProgress(progress);
              }
              break;
            }
            case 'recording_request':
              void handleRecordingRequest(ws, msg.data);
              break;
          }
        } catch {
          // Ignore malformed messages
        }
      };

      ws.onclose = () => {
        wsRef.current = null;
        // Only reconnect if still connected
        if (useDroneStore.getState().connectionStatus === 'connected') {
          reconnectTimerRef.current = setTimeout(() => {
            backoffRef.current = Math.min(backoffRef.current * 2, MAX_BACKOFF);
            connect();
          }, backoffRef.current);
        }
      };

      ws.onerror = () => {
        ws.close();
      };
    }

    const unsubscribeRecorderStatus = useDroneStore.subscribe((state, previousState) => {
      if (state.recordingReady === previousState.recordingReady) return;
      const ws = wsRef.current;
      if (ws?.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({
          type: 'recorder_status',
          data: { ready: state.recordingReady },
        }));
      }
    });

    connect();

    return () => {
      unsubscribeRecorderStatus();
      if (wsRef.current) {
        wsRef.current.close();
        wsRef.current = null;
      }
      if (reconnectTimerRef.current) {
        clearTimeout(reconnectTimerRef.current);
        reconnectTimerRef.current = null;
      }
    };
  }, [connectionStatus, previewMode, setTelemetry, addCommandLog, setSequenceProgress, setIsFlying]);
}
