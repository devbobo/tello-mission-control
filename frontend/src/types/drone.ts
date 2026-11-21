export type ConnectionStatus = 'disconnected' | 'connecting' | 'connected' | 'error';

export interface TelemetryData {
  battery: number;
  height: number;
  flight_time: number;
  temperature: { high: number; low: number };
  attitude: { pitch: number; roll: number; yaw: number };
  speed: { x: number; y: number; z: number };
  barometer: number;
  tof_distance: number;
}

export interface CommandLogEntry {
  command: string;
  params: Record<string, unknown>;
  result: 'ok' | 'error';
  timestamp: string;
  error?: string;
}

export interface FlightSession {
  id: string;
  started_at: string;
  ended_at: string | null;
  status: 'active' | 'completed' | 'interrupted';
  event_count: number;
  video_available: boolean;
  video_started_at: string | null;
  video_duration_ms: number | null;
}

export interface FlightEvent {
  id: number;
  session_id: string;
  event_type: 'command' | 'telemetry';
  occurred_at: string;
  command: string | null;
  params: Record<string, unknown>;
  result: 'ok' | 'error' | null;
  error: string | null;
  telemetry: TelemetryData | null;
}

export interface FlightEventPage {
  items: FlightEvent[];
  total: number;
  limit: number;
  offset: number;
}

export interface Sequence {
  id: string;
  name: string;
  description: string;
  steps: number;
}

export interface SequenceProgress {
  sequence_id: string;
  current_step: number;
  total_steps: number;
  step_description: string;
  status: 'running' | 'completed' | 'cancelled' | 'error';
}

export type MoveDirection = 'forward' | 'back' | 'left' | 'right' | 'up' | 'down';
export type RotateDirection = 'cw' | 'ccw';
export type FlipDirection = 'forward' | 'back' | 'left' | 'right';

export interface ApiResponse {
  ok: boolean;
  message?: string;
  error?: string;
}

export interface ConnectResponse {
  ok: boolean;
  status: string;
  battery: number;
}

export interface StatusResponse {
  connected: boolean;
  flying: boolean;
  streaming: boolean;
  battery: number;
}

export interface WebRtcAnswer {
  sdp: string;
  type: 'answer';
  peer_id: string;
}

export interface WebRtcIceServer {
  urls: string | string[];
  username?: string;
  credential?: string;
}

export interface WebRtcConfiguration {
  iceServers: WebRtcIceServer[];
}

export type RecordingRequestAction = 'start' | 'stop';

export interface RecordingRequest {
  request_id: string;
  action: RecordingRequestAction;
}

export type WsMessage =
  | { type: 'telemetry'; data: TelemetryData; timestamp?: string }
  | { type: 'command_log'; data: CommandLogEntry; timestamp?: string }
  | { type: 'sequence_progress'; data: SequenceProgress; timestamp?: string }
  | { type: 'recording_request'; data: RecordingRequest };
