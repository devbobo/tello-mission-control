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

export interface WsMessage {
  type: 'telemetry' | 'command_log' | 'sequence_progress';
  data: TelemetryData | CommandLogEntry | SequenceProgress;
  timestamp?: string;
}
