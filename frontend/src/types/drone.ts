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

export interface VisionDetection {
  label: string;
  confidence: number;
  x_min: number;
  y_min: number;
  x_max: number;
  y_max: number;
  track_id?: number | null;
}

export interface VisionFrameData {
  frame_id: number;
  frame_width: number;
  frame_height: number;
  model: string;
  device: string;
  inference_ms: number;
  detections: VisionDetection[];
}

export interface VisionFrame {
  data: VisionFrameData;
  timestamp: string;
}

export interface OdometryData {
  frame_id: number;
  frame_width: number;
  frame_height: number;
  position_x: number;
  position_y: number;
  delta_x: number;
  delta_y: number;
  tracking_valid: boolean;
  tracked_points: number;
  quality: number;
}

export interface OdometryFrame {
  data: OdometryData;
  timestamp: string;
}

export interface MarkerDetection {
  marker_type: 'qr' | 'aruco';
  marker_id: string;
  payload: string | null;
  payload_truncated: boolean;
  x_min: number;
  y_min: number;
  x_max: number;
  y_max: number;
}

export interface MarkerFrameData {
  frame_id: number;
  frame_width: number;
  frame_height: number;
  inference_ms: number;
  aruco_dictionary: string;
  markers: MarkerDetection[];
}

export interface MarkerFrame {
  data: MarkerFrameData;
  timestamp: string;
}

export type WsMessage =
  | { type: 'telemetry'; data: TelemetryData; timestamp: string }
  | { type: 'vision'; data: VisionFrameData; timestamp: string }
  | { type: 'odometry'; data: OdometryData; timestamp: string }
  | { type: 'markers'; data: MarkerFrameData; timestamp: string }
  | { type: 'command_log'; data: CommandLogEntry }
  | { type: 'sequence_progress'; data: SequenceProgress }
  | { type: 'recording_request'; data: RecordingRequest };

export type RecordingRequestAction = 'start' | 'stop';

export interface RecordingRequest {
  request_id: string;
  action: RecordingRequestAction;
}
