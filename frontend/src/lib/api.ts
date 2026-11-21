import type {
  ApiResponse,
  ConnectResponse,
  FlightEventPage,
  FlightSession,
  FlipDirection,
  MoveDirection,
  RotateDirection,
  Sequence,
  StatusResponse,
  WebRtcAnswer,
  WebRtcConfiguration,
} from '@/types/drone';

async function post<T>(
  path: string,
  body?: Record<string, unknown>,
  signal?: AbortSignal,
): Promise<T> {
  try {
    const res = await fetch(path, {
      method: 'POST',
      headers: body ? { 'Content-Type': 'application/json' } : undefined,
      body: body ? JSON.stringify(body) : undefined,
      signal,
    });
    if (!res.ok) {
      const text = await res.text().catch(() => 'Unknown error');
      return { ok: false, error: `HTTP ${res.status}: ${text}` } as T;
    }
    return await res.json();
  } catch (err) {
    return { ok: false, error: err instanceof Error ? err.message : 'Network error' } as T;
  }
}

async function get<T>(path: string): Promise<T> {
  try {
    const res = await fetch(path);
    if (!res.ok) {
      throw new Error(`HTTP ${res.status}`);
    }
    return await res.json();
  } catch (err) {
    throw err instanceof Error ? err : new Error('Network error');
  }
}

export function connectDrone(): Promise<ConnectResponse> {
  return post<ConnectResponse>('/api/control/connect');
}

export function disconnectDrone(): Promise<ApiResponse> {
  return post<ApiResponse>('/api/control/disconnect');
}

export function takeoff(): Promise<ApiResponse> {
  return post<ApiResponse>('/api/control/takeoff');
}

export function land(): Promise<ApiResponse> {
  return post<ApiResponse>('/api/control/land');
}

export function emergencyStop(): Promise<ApiResponse> {
  return post<ApiResponse>('/api/control/emergency');
}

export function move(direction: MoveDirection, distance_cm: number): Promise<ApiResponse> {
  return post<ApiResponse>('/api/control/move', { direction, distance_cm });
}

export function rotate(direction: RotateDirection, angle_deg: number): Promise<ApiResponse> {
  return post<ApiResponse>('/api/control/rotate', { direction, angle_deg });
}

export function flip(direction: FlipDirection): Promise<ApiResponse> {
  return post<ApiResponse>('/api/control/flip', { direction });
}

export function sendRc(lr: number, fb: number, ud: number, yaw: number): Promise<ApiResponse> {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 1000);
  return post<ApiResponse>('/api/control/rc', { lr, fb, ud, yaw }, controller.signal)
    .finally(() => clearTimeout(timeout));
}

export function getStatus(): Promise<StatusResponse> {
  return get<StatusResponse>('/api/status');
}

export async function takeSnapshot(): Promise<Blob> {
  const res = await fetch('/api/video/snapshot', { method: 'POST' });
  if (!res.ok) {
    throw new Error(`Snapshot failed: HTTP ${res.status}`);
  }
  return res.blob();
}

export async function createWebRtcOffer(sdp: string): Promise<WebRtcAnswer> {
  const res = await fetch('/api/video/webrtc/offer', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ sdp, type: 'offer' }),
  });
  if (!res.ok) {
    const body = await res.json().catch(() => null) as { detail?: string } | null;
    throw new Error(body?.detail ?? `WebRTC negotiation failed: HTTP ${res.status}`);
  }
  return res.json() as Promise<WebRtcAnswer>;
}

export function getWebRtcConfiguration(): Promise<WebRtcConfiguration> {
  return get<WebRtcConfiguration>('/api/video/webrtc/config');
}

export async function closeWebRtcPeer(peerId: string): Promise<void> {
  const res = await fetch(`/api/video/webrtc/${encodeURIComponent(peerId)}`, {
    method: 'DELETE',
  });
  if (!res.ok) {
    throw new Error(`Failed to close WebRTC peer: HTTP ${res.status}`);
  }
}

export function getSequences(): Promise<Sequence[]> {
  return get<Sequence[]>('/api/sequences');
}

export function getFlightSessions(): Promise<FlightSession[]> {
  return get<FlightSession[]>('/api/flights?limit=100');
}

export function getActiveFlight(): Promise<FlightSession | null> {
  return get<FlightSession | null>('/api/flights/active');
}

export async function startNextFlightSession(flightId: string): Promise<FlightSession> {
  const res = await fetch(`/api/flights/${encodeURIComponent(flightId)}/next`, {
    method: 'POST',
  });
  if (!res.ok) {
    const body = await res.json().catch(() => null) as { detail?: string } | null;
    throw new Error(body?.detail ?? `Unable to start next flight: HTTP ${res.status}`);
  }
  return res.json() as Promise<FlightSession>;
}

export function getFlightEvents(
  flightId: string,
  limit = 100,
  offset = 0,
): Promise<FlightEventPage> {
  const params = new URLSearchParams({ limit: String(limit), offset: String(offset) });
  return get<FlightEventPage>(
    `/api/flights/${encodeURIComponent(flightId)}/events?${params.toString()}`,
  );
}

export async function getAllFlightEvents(
  flightId: string,
  initialPage?: FlightEventPage,
): Promise<FlightEventPage['items']> {
  const firstPage = initialPage ?? await getFlightEvents(flightId, 500, 0);
  if (firstPage.total <= firstPage.items.length) return firstPage.items;

  const pageOffsets = [];
  for (let offset = firstPage.items.length; offset < firstPage.total; offset += 500) {
    pageOffsets.push(offset);
  }
  const remainingPages = await Promise.all(
    pageOffsets.map((offset) => getFlightEvents(flightId, 500, offset)),
  );
  return [...firstPage.items, ...remainingPages.flatMap((page) => page.items)];
}

export function getFlightVideoUrl(flightId: string): string {
  return `/api/flights/${encodeURIComponent(flightId)}/video`;
}

export async function uploadFlightVideo(
  flightId: string,
  video: Blob,
  startedAt: string,
  durationMs: number,
  recordingId?: string,
): Promise<void> {
  const params = new URLSearchParams({
    started_at: startedAt,
    duration_ms: String(durationMs),
  });
  if (recordingId) params.set('recording_id', recordingId);
  let response: Response;
  try {
    response = await fetch(
      `/api/flights/${encodeURIComponent(flightId)}/video?${params.toString()}`,
      {
        method: 'PUT',
        headers: { 'Content-Type': video.type || 'video/webm' },
        body: video,
      },
    );
  } catch (error) {
    throw new Error(error instanceof Error ? error.message : 'Flight video upload failed');
  }
  if (!response.ok) {
    const body = await response.json().catch(() => null) as { detail?: string } | null;
    throw new Error(body?.detail ?? `Flight video upload failed: HTTP ${response.status}`);
  }
}

export function runSequence(id: string): Promise<ApiResponse> {
  return post<ApiResponse>(`/api/sequences/${encodeURIComponent(id)}/run`);
}

export function cancelSequence(): Promise<ApiResponse> {
  return post<ApiResponse>('/api/sequences/cancel');
}

export function startVideoStream(): Promise<ApiResponse> {
  return post<ApiResponse>('/api/video/stream/start');
}

export function stopVideoStream(): Promise<ApiResponse> {
  return post<ApiResponse>('/api/video/stream/stop');
}
