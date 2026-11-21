import { useCallback, useEffect, useRef, useState } from 'react';
import { Clock3, Maximize2, Minimize2, Pause, Play, X } from 'lucide-react';
import { batteryTextColor } from '@/lib/format';
import { ReplayActionButtons } from '@/components/ActionButtons';
import EmergencyButton from '@/components/EmergencyButton';
import FlightControls from '@/components/FlightControls';
import * as api from '@/lib/api';
import TelemetryPanel from '@/components/TelemetryPanel';
import Vignette from '@/components/Vignette';
import type { FlightEvent, FlightSession, TelemetryData } from '@/types/drone';

interface FlightHistoryModalProps {
  isOpen: boolean;
  onClose: () => void;
}

function formatTime(value: string): string {
  return new Date(value).toLocaleTimeString();
}

function formatSession(value: string): string {
  return new Date(value).toLocaleString();
}

function eventSummary(event: FlightEvent): string {
  if (event.event_type === 'command') {
    if (event.command === 'recording_start') return 'Recording started';
    if (event.command === 'recording_stop') return 'Recording stopped';
    const params = Object.entries(event.params)
      .map(([key, value]) => `${key}: ${String(value)}`)
      .join(', ');
    return [event.command, params].filter(Boolean).join(' · ');
  }

  const telemetry = event.telemetry;
  if (!telemetry) return 'Telemetry snapshot';
  return `Battery ${telemetry.battery}% · Altitude ${telemetry.height} cm · Flight ${telemetry.flight_time}s`;
}

function telemetryAtPlaybackTime(
  events: FlightEvent[],
  startedAt: string,
  playbackSeconds: number,
): TelemetryData | null {
  const playbackTimestamp = Date.parse(startedAt) + playbackSeconds * 1000;
  let latest: TelemetryData | null = null;
  for (const event of events) {
    if (Date.parse(event.occurred_at) > playbackTimestamp) break;
    if (event.event_type === 'telemetry' && event.telemetry) latest = event.telemetry;
  }
  return latest;
}

interface ReplayControlHighlight {
  highlightedControls: string[];
  result: 'ok' | 'error' | null;
  params: Record<string, unknown>;
}

const CONTROL_HIGHLIGHT_DURATION_MS = 1500;

function controlIdsForEvent(event: FlightEvent): string[] {
  if (event.event_type !== 'command') return [];
  if (event.command === 'takeoff' || event.command === 'land' || event.command === 'emergency') {
    return [event.command];
  }

  if (event.command === 'move') {
    switch (event.params.direction) {
      case 'forward':
      case 'back':
      case 'left':
      case 'right':
      case 'up':
      case 'down':
        return [`move_${event.params.direction}`];
      default:
        return [];
    }
  }

  if (event.command === 'rotate') {
    switch (event.params.direction) {
      case 'cw':
        return ['rotate_cw'];
      case 'ccw':
        return ['rotate_ccw'];
      default:
        return [];
    }
  }

  if (event.command === 'flip') {
    switch (event.params.direction) {
      case 'forward':
      case 'back':
      case 'left':
      case 'right':
        return [`flip_${event.params.direction}`];
      default:
        return [];
    }
  }

  if (event.command === 'rc_control') {
    const controls: string[] = [];
    const lr = typeof event.params.lr === 'number' ? event.params.lr : 0;
    const fb = typeof event.params.fb === 'number' ? event.params.fb : 0;
    const ud = typeof event.params.ud === 'number' ? event.params.ud : 0;
    const yaw = typeof event.params.yaw === 'number' ? event.params.yaw : 0;
    if (fb > 0) controls.push('move_forward');
    if (fb < 0) controls.push('move_back');
    if (lr > 0) controls.push('move_right');
    if (lr < 0) controls.push('move_left');
    if (ud > 0) controls.push('move_up');
    if (ud < 0) controls.push('move_down');
    if (yaw > 0) controls.push('rotate_cw');
    if (yaw < 0) controls.push('rotate_ccw');
    return controls;
  }

  return [];
}

function controlHighlightAtPlaybackTime(
  events: FlightEvent[],
  startedAt: string,
  playbackSeconds: number,
): ReplayControlHighlight | null {
  const playbackTimestamp = Date.parse(startedAt) + playbackSeconds * 1000;
  let latest: { event: FlightEvent; timestamp: number; controls: string[] } | null = null;
  for (const event of events) {
    const timestamp = Date.parse(event.occurred_at);
    if (!Number.isFinite(timestamp)) continue;
    if (timestamp > playbackTimestamp) break;
    const controls = controlIdsForEvent(event);
    if (controls.length > 0) latest = { event, timestamp, controls };
  }

  if (!latest || playbackTimestamp - latest.timestamp > CONTROL_HIGHLIGHT_DURATION_MS) {
    return null;
  }

  return {
    highlightedControls: latest.controls,
    result: latest.event.result,
    params: latest.event.params,
  };
}

function lastCommandAtPlaybackTime(
  events: FlightEvent[],
  startedAt: string,
  playbackSeconds: number,
): number | null {
  const playbackTimestamp = Date.parse(startedAt) + playbackSeconds * 1000;
  let latest: { id: number; timestamp: number } | null = null;
  for (const event of events) {
    if (event.event_type !== 'command') continue;
    const timestamp = Date.parse(event.occurred_at);
    if (!Number.isFinite(timestamp) || timestamp > playbackTimestamp) continue;
    if (!latest || timestamp >= latest.timestamp) latest = { id: event.id, timestamp };
  }
  return latest?.id ?? null;
}

function formatPlaybackTime(value: number): string {
  const seconds = Math.max(0, Math.floor(value));
  return `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, '0')}`;
}

export default function FlightHistoryModal({ isOpen, onClose }: FlightHistoryModalProps) {
  const [sessions, setSessions] = useState<FlightSession[]>([]);
  const [selectedId, setSelectedId] = useState('');
  const [events, setEvents] = useState<FlightEvent[]>([]);
  const [replayEvents, setReplayEvents] = useState<FlightEvent[]>([]);
  const [playbackTime, setPlaybackTime] = useState(0);
  const [playbackDuration, setPlaybackDuration] = useState(0);
  const [isPlaying, setIsPlaying] = useState(false);
  const [total, setTotal] = useState(0);
  const [loadingSessions, setLoadingSessions] = useState(false);
  const [loadingEvents, setLoadingEvents] = useState(false);
  const [error, setError] = useState('');
  const [fullScreenReplay, setFullScreenReplay] = useState(false);
  const videoRef = useRef<HTMLVideoElement>(null);
  const activeTimelineActionRef = useRef<HTMLButtonElement>(null);

  const loadSessions = useCallback(async () => {
    setLoadingSessions(true);
    setError('');
    try {
      const result = await api.getFlightSessions();
      setSessions(result);
      setSelectedId((current) =>
        result.some((session) => session.id === current) ? current : result[0]?.id ?? '',
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unable to load flight history');
    } finally {
      setLoadingSessions(false);
    }
  }, []);

  useEffect(() => {
    if (!isOpen) return;
    void loadSessions();
  }, [isOpen, loadSessions]);

  useEffect(() => {
    if (!isOpen) setFullScreenReplay(false);
  }, [isOpen]);

  useEffect(() => {
    if (!isOpen || !selectedId) {
      setEvents([]);
      setReplayEvents([]);
      setTotal(0);
      return;
    }
    let cancelled = false;
    setLoadingEvents(true);
    setEvents([]);
    setReplayEvents([]);
    setPlaybackTime(0);
    setPlaybackDuration(0);
    setIsPlaying(false);
    setTotal(0);
    setError('');
    api.getFlightEvents(selectedId).then(async (page) => {
        if (cancelled) return;
        setEvents(page.items);
        setTotal(page.total);
        const selected = sessions.find((session) => session.id === selectedId);
        if (selected?.video_available) {
          const allEvents = await api.getAllFlightEvents(selectedId, page);
          if (!cancelled) setReplayEvents(allEvents);
        } else {
          setReplayEvents(page.items);
        }
      }).catch(
      (err: unknown) => {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : 'Unable to load flight events');
        }
      },
    ).finally(() => {
      if (!cancelled) setLoadingEvents(false);
    });
    return () => {
      cancelled = true;
    };
  }, [isOpen, selectedId, sessions]);

  useEffect(() => {
    if (!isOpen) return;
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key !== 'Escape') return;
      if (fullScreenReplay) {
        setFullScreenReplay(false);
      } else {
        onClose();
      }
    };
    document.addEventListener('keydown', handleKeyDown);
    return () => document.removeEventListener('keydown', handleKeyDown);
  }, [isOpen, onClose, fullScreenReplay]);

  const loadMore = async () => {
    if (!selectedId) return;
    setLoadingEvents(true);
    setError('');
    try {
      const page = await api.getFlightEvents(selectedId, 100, events.length);
      setEvents((current) => [...current, ...page.items]);
      setTotal(page.total);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unable to load more flight events');
    } finally {
      setLoadingEvents(false);
    }
  };

  const currentSession = sessions.find((session) => session.id === selectedId);
  const currentVideoStartedAt = currentSession?.video_started_at;
  const replayActionEvents = replayEvents.length > events.length ? replayEvents : events;
  const lastActionEventId =
    fullScreenReplay && currentVideoStartedAt
      ? lastCommandAtPlaybackTime(replayActionEvents, currentVideoStartedAt, playbackTime)
      : null;

  useEffect(() => {
    if (!fullScreenReplay) return;
    activeTimelineActionRef.current?.scrollIntoView({
      block: 'nearest',
      inline: 'nearest',
      behavior: 'smooth',
    });
  }, [fullScreenReplay, lastActionEventId]);

  if (!isOpen) return null;

  const selectedSession = currentSession;
  const videoStartedAt = selectedSession?.video_started_at;
  const currentTelemetry = videoStartedAt
    ? telemetryAtPlaybackTime(replayEvents, videoStartedAt, playbackTime)
    : null;
  const currentControlHighlight = videoStartedAt
    ? controlHighlightAtPlaybackTime(replayEvents, videoStartedAt, playbackTime)
    : null;
  const durationSeconds =
    playbackDuration || (selectedSession?.video_duration_ms ?? 0) / 1000;
  const replayControls = {
    highlightedControls: currentControlHighlight?.highlightedControls ?? [],
    result: currentControlHighlight?.result ?? null,
    params: currentControlHighlight?.params ?? {},
    telemetry: currentTelemetry,
  };

  const seekToEvent = (event: FlightEvent) => {
    if (!videoStartedAt || !videoRef.current) return;
    const offsetSeconds = (Date.parse(event.occurred_at) - Date.parse(videoStartedAt)) / 1000;
    const duration = videoRef.current.duration;
    if (offsetSeconds < 0 || (Number.isFinite(duration) && offsetSeconds > duration)) return;
    videoRef.current.currentTime = offsetSeconds;
    void videoRef.current.play();
  };

  const togglePlayback = () => {
    const video = videoRef.current;
    if (!video) return;
    if (isPlaying) {
      video.pause();
      setIsPlaying(false);
    } else {
      void video.play().then(
        () => setIsPlaying(true),
        (playError: unknown) => {
          setError(playError instanceof Error ? playError.message : 'Unable to play flight recording');
        },
      );
    }
  };

  const seekPlayback = (time: number) => {
    if (!videoRef.current) return;
    videoRef.current.currentTime = time;
    setPlaybackTime(time);
  };

  const playbackControls = (
    <div
      className={`flex items-center gap-3 rounded-lg border border-white/10 bg-black/85 px-3 py-2 shadow-xl backdrop-blur-md ${
        fullScreenReplay
          ? 'pointer-events-auto fixed bottom-[7rem] left-1/2 z-[4] w-[min(640px,calc(100vw-2rem))] -translate-x-1/2'
          : 'mt-2 w-full'
      }`}
    >
      <button
        className="control-btn flex h-8 w-8 shrink-0 items-center justify-center"
        onClick={togglePlayback}
        aria-label={isPlaying ? 'Pause flight recording' : 'Play flight recording'}
      >
        {isPlaying ? <Pause size={15} /> : <Play size={15} />}
      </button>
      <span className="shrink-0 font-mono text-[10px] text-hud-secondary">
        {formatPlaybackTime(playbackTime)}
      </span>
      <input
        className="min-w-0 flex-1 accent-info"
        type="range"
        min={0}
        max={Math.max(durationSeconds, 0.1)}
        step={0.1}
        value={Math.min(playbackTime, durationSeconds)}
        disabled={durationSeconds <= 0}
        onChange={(event) => seekPlayback(Number(event.currentTarget.value))}
        aria-label="Seek flight recording"
      />
      <span className="shrink-0 font-mono text-[10px] text-hud-secondary">
        {formatPlaybackTime(durationSeconds)}
      </span>
    </div>
  );

  const timelineSourceEvents =
    fullScreenReplay && replayEvents.length > events.length ? replayEvents : events;
  const timelineEvents = fullScreenReplay
    ? timelineSourceEvents.filter((event) => event.event_type === 'command')
    : events;

  const timelineContent = loadingSessions && sessions.length === 0 ? (
    <p className="py-8 text-center text-hud-xs text-hud-dim">Loading sessions…</p>
  ) : !selectedSession ? (
    <p className="py-8 text-center text-hud-xs text-hud-dim">
      {error ? 'Flight history could not be loaded.' : 'No flight sessions recorded yet.'}
    </p>
  ) : loadingEvents && timelineEvents.length === 0 ? (
    <p className="py-8 text-center text-hud-xs text-hud-dim">Loading timeline…</p>
  ) : timelineEvents.length === 0 ? (
    <p className="py-8 text-center text-hud-xs text-hud-dim">
      {fullScreenReplay
        ? 'No command events recorded for this flight.'
        : 'No events recorded for this flight.'}
    </p>
  ) : (
    <ol className="divide-y divide-white/[0.06]">
      {timelineEvents.map((event) => {
        const isLastAction = fullScreenReplay && event.id === lastActionEventId;
        return (
          <li key={event.id}>
            <button
              ref={isLastAction ? activeTimelineActionRef : undefined}
              className={`flex w-full items-start gap-3 px-3 py-2.5 text-left hover:bg-white/[0.04] disabled:cursor-default ${
                fullScreenReplay
                  ? isLastAction
                    ? 'bg-white/[0.06] opacity-100'
                    : 'opacity-40'
                  : ''
              }`}
              disabled={!selectedSession.video_available}
              data-replay-active={isLastAction || undefined}
              onClick={() => seekToEvent(event)}
              aria-label={`Seek to ${eventSummary(event)} at ${formatTime(event.occurred_at)}`}
            >
              <time className="w-20 shrink-0 pt-0.5 font-mono text-[10px] text-hud-dim">
                {formatTime(event.occurred_at)}
              </time>
              <span
                className={`mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full ${
                  event.event_type === 'telemetry'
                    ? 'bg-info'
                    : event.result === 'error'
                      ? 'bg-danger'
                      : 'bg-ok'
                }`}
              />
              <div className="min-w-0 flex-1">
                <p className="text-hud-xs text-white">{eventSummary(event)}</p>
                {event.error && <p className="mt-1 text-[10px] text-danger">{event.error}</p>}
              </div>
              <span className="shrink-0 text-[9px] uppercase tracking-wider text-hud-dim">
                {event.event_type === 'command' ? event.result : 'telemetry'}
              </span>
            </button>
          </li>
        );
      })}
    </ol>
  );

  return (
    <div
      className={
        fullScreenReplay
          ? 'fixed inset-0 z-[5] bg-black'
          : 'fixed inset-0 z-[5] flex items-center justify-center bg-black/70 p-4 backdrop-blur-sm'
      }
      onClick={onClose}
      role="presentation"
    >
      <section
        className={
          fullScreenReplay
            ? 'relative h-full w-full'
            : 'hud-panel flex w-full max-h-[85vh] max-w-2xl flex-col'
        }
        onClick={(event) => event.stopPropagation()}
        aria-label={fullScreenReplay ? 'Full-screen flight replay' : 'Flight history'}
        aria-modal="true"
        role="dialog"
      >
        <div className={`mb-4 flex items-center justify-between gap-4 ${fullScreenReplay ? 'hidden' : ''}`}>
          <div className="flex items-center gap-2">
            <Clock3 size={16} className="text-info" />
            <h2 className="hud-label text-hud-lg">FLIGHT HISTORY</h2>
          </div>
          <div className="flex items-center gap-2">
            {selectedSession?.video_available && (
              <button
                className="control-btn flex items-center gap-2 px-2 py-1 text-[10px]"
                onClick={() => setFullScreenReplay(true)}
                aria-label="Enter full-screen replay"
              >
                <Maximize2 size={14} />
                <span className="hidden sm:inline">FULL-SCREEN REPLAY</span>
              </button>
            )}
            <button className="control-btn p-1" onClick={onClose} aria-label="Close flight history">
              <X size={16} />
            </button>
          </div>
        </div>

        {sessions.length > 0 && (
          <label className={`mb-3 text-hud-xs text-hud-secondary ${fullScreenReplay ? 'hidden' : ''}`}>
            Session
            <select
              className="mt-1 w-full rounded-md border border-white/10 bg-black/70 px-3 py-2 text-sm text-white"
              value={selectedId}
              disabled={loadingEvents}
              onChange={(event) => {
                const nextId = event.target.value;
                if (!sessions.find((session) => session.id === nextId)?.video_available) {
                  setFullScreenReplay(false);
                }
                setSelectedId(nextId);
              }}
            >
              {sessions.map((session) => (
                <option key={session.id} value={session.id}>
                  {formatSession(session.started_at)} · {session.event_count} events · {session.status}
                </option>
              ))}
            </select>
          </label>
        )}

        {error && (
          <p className={`mb-3 text-hud-xs text-danger ${fullScreenReplay ? 'hidden' : ''}`} role="alert">
            {error}
          </p>
        )}

        <div
          className={`min-h-0 flex-1 ${
            fullScreenReplay ? 'contents' : 'flex flex-col'
          }`}
        >
          {selectedSession?.video_available && (
            <div
              className={`${
                fullScreenReplay
                  ? 'fixed inset-0 z-0 bg-black'
                  : 'mb-3 rounded-lg border border-white/[0.06] bg-black/40 p-2'
              }`}
            >
              <video
                ref={videoRef}
                className={`rounded bg-black ${
                  fullScreenReplay
                    ? 'h-full w-full object-contain'
                    : 'h-auto w-full'
                }`}
                src={api.getFlightVideoUrl(selectedSession.id)}
                playsInline
                aria-label="Flight recording"
                onTimeUpdate={(event) => setPlaybackTime(event.currentTarget.currentTime)}
                onSeeked={(event) => setPlaybackTime(event.currentTarget.currentTime)}
                onLoadedMetadata={(event) => {
                  if (Number.isFinite(event.currentTarget.duration)) {
                    setPlaybackDuration(event.currentTarget.duration);
                  }
                }}
                onPlay={() => setIsPlaying(true)}
                onPause={() => setIsPlaying(false)}
                onEnded={() => setIsPlaying(false)}
              />
              {!fullScreenReplay && playbackControls}
              <div
                className={`mt-2 flex flex-wrap items-center justify-between gap-3 text-[10px] text-hud-dim ${
                  fullScreenReplay ? 'hidden' : ''
                }`}
              >
                {currentTelemetry ? (
                  <span aria-live="polite">
                    BAT {currentTelemetry.battery}% · ALT {currentTelemetry.height} cm · FLIGHT{' '}
                    {currentTelemetry.flight_time}s · YAW {currentTelemetry.attitude.yaw}°
                  </span>
                ) : (
                  <span>NO TELEMETRY AT PLAYHEAD</span>
                )}
              </div>
            </div>
          )}
          {fullScreenReplay && selectedSession?.video_available && playbackControls}

          {!fullScreenReplay && (
            <div className="min-h-0 flex-1 overflow-y-auto rounded-lg border border-white/[0.06]">
              {timelineContent}
            </div>
          )}
        </div>

        {!fullScreenReplay && (
          <div className="mt-3 flex items-center justify-between text-[10px] text-hud-dim">
          <span>
            {selectedSession
              ? `${events.length} of ${total} events · ${selectedSession.status}`
              : 'Read-only timeline'}
          </span>
          {events.length < total && (
            <button
              className="control-btn px-3 py-1.5 text-[10px]"
              disabled={loadingEvents}
              onClick={() => void loadMore()}
            >
              {loadingEvents ? 'Loading…' : 'Load more'}
            </button>
          )}
          </div>
        )}

        {fullScreenReplay && (
          <>
            <Vignette />
            <div
              className="pointer-events-none fixed inset-0 z-[2] grid"
              style={{
                padding: 'clamp(8px, 1vw, 16px)',
                gap: 'clamp(4px, 0.5vw, 8px)',
                gridTemplateColumns: 'minmax(180px, 220px) 1fr minmax(200px, 260px)',
                gridTemplateRows: 'minmax(0, 1fr) auto',
                gridTemplateAreas: `
                  "telemetry . status"
                  "controls . ."
                `,
              }}
            >
              <div className="pointer-events-auto self-start" style={{ gridArea: 'telemetry' }}>
                <TelemetryPanel telemetryOverride={currentTelemetry} />
              </div>

              <div
                className="pointer-events-auto self-end max-h-[calc(100vh-300px)] overflow-y-auto"
                style={{ gridArea: 'controls' }}
              >
                <FlightControls replay={replayControls} />
              </div>

              <div
                className="pointer-events-auto self-start justify-self-end flex max-h-full w-full max-w-[260px] flex-col gap-2 overflow-y-auto"
                style={{ gridArea: 'status' }}
              >
                <div className="hud-panel animate-fade-in-up flex flex-row items-center gap-3">
                  <span className="w-2 h-2 flex-shrink-0 rounded-full bg-info" />
                  <span className="font-mono uppercase text-hud-sm tracking-[0.08em]">replay</span>
                  {currentTelemetry && (
                    <>
                      <span className="h-4 w-px bg-white/10" />
                      <span className={`font-mono text-hud-sm ${batteryTextColor(currentTelemetry.battery)}`}>
                        {currentTelemetry.battery}%
                      </span>
                    </>
                  )}
                  <span className="h-4 w-px bg-white/10" />
                  <span className="text-hud-secondary font-mono text-hud-sm">TELLO</span>
                  <button
                    className="control-btn p-1"
                    onClick={() => setFullScreenReplay(false)}
                    aria-label="Exit full-screen replay"
                    title="Exit full-screen replay"
                  >
                    <Minimize2 size={16} />
                  </button>
                  <button
                    className="control-btn p-1"
                    onClick={onClose}
                    aria-label="Close flight history"
                  >
                    <X size={16} />
                  </button>
                </div>

                <div className="hud-panel max-h-[calc(100vh-96px)] w-full overflow-y-auto !p-0">
                  <div className="flex items-center justify-between gap-2 border-b border-white/[0.06] px-3 py-2">
                    <span className="hud-label">Flight Timeline</span>
                    <span className="text-[9px] text-hud-dim">
                      {timelineEvents.length} commands shown
                    </span>
                  </div>
                  {error && <p className="px-3 py-2 text-hud-xs text-danger" role="alert">{error}</p>}
                  {timelineContent}
                  {!fullScreenReplay && events.length < total && (
                    <div className="border-t border-white/[0.06] p-2">
                      <button
                        className="control-btn w-full px-3 py-1.5 text-[10px]"
                        disabled={loadingEvents}
                        onClick={() => void loadMore()}
                      >
                        {loadingEvents ? 'Loading…' : 'Load more'}
                      </button>
                    </div>
                  )}
                </div>
              </div>
            </div>
            <div className="pointer-events-auto fixed bottom-3 left-1/2 z-[2] -translate-x-1/2 sm:bottom-5">
              <ReplayActionButtons
                highlightedControls={replayControls.highlightedControls}
                result={replayControls.result}
              />
            </div>
            <EmergencyButton
              replay={{
                highlighted: replayControls.highlightedControls.includes('emergency'),
              }}
            />
          </>
        )}
      </section>
    </div>
  );
}
