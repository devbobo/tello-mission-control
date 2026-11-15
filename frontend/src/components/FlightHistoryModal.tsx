import { useCallback, useEffect, useState } from 'react';
import { Clock3, X } from 'lucide-react';
import * as api from '@/lib/api';
import type { FlightEvent, FlightSession } from '@/types/drone';

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
    const params = Object.entries(event.params)
      .map(([key, value]) => `${key}: ${String(value)}`)
      .join(', ');
    return [event.command, params].filter(Boolean).join(' · ');
  }

  const telemetry = event.telemetry;
  if (!telemetry) return 'Telemetry snapshot';
  return `Battery ${telemetry.battery}% · Altitude ${telemetry.height} cm · Flight ${telemetry.flight_time}s`;
}

export default function FlightHistoryModal({ isOpen, onClose }: FlightHistoryModalProps) {
  const [sessions, setSessions] = useState<FlightSession[]>([]);
  const [selectedId, setSelectedId] = useState('');
  const [events, setEvents] = useState<FlightEvent[]>([]);
  const [total, setTotal] = useState(0);
  const [loadingSessions, setLoadingSessions] = useState(false);
  const [loadingEvents, setLoadingEvents] = useState(false);
  const [error, setError] = useState('');

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
    if (!isOpen || !selectedId) {
      setEvents([]);
      setTotal(0);
      return;
    }
    let cancelled = false;
    setLoadingEvents(true);
    setEvents([]);
    setTotal(0);
    setError('');
    api.getFlightEvents(selectedId).then(
      (page) => {
        if (cancelled) return;
        setEvents(page.items);
        setTotal(page.total);
      },
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
  }, [isOpen, selectedId]);

  useEffect(() => {
    if (!isOpen) return;
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose();
    };
    document.addEventListener('keydown', handleKeyDown);
    return () => document.removeEventListener('keydown', handleKeyDown);
  }, [isOpen, onClose]);

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

  if (!isOpen) return null;

  const selectedSession = sessions.find((session) => session.id === selectedId);

  return (
    <div
      className="fixed inset-0 bg-black/70 backdrop-blur-sm z-[5] flex items-center justify-center p-4"
      onClick={onClose}
      role="presentation"
    >
      <section
        className="hud-panel w-full max-w-2xl max-h-[85vh] flex flex-col"
        onClick={(event) => event.stopPropagation()}
        aria-label="Flight history"
        aria-modal="true"
        role="dialog"
      >
        <div className="flex items-center justify-between gap-4 mb-4">
          <div className="flex items-center gap-2">
            <Clock3 size={16} className="text-info" />
            <h2 className="hud-label text-hud-lg">FLIGHT HISTORY</h2>
          </div>
          <button className="control-btn p-1" onClick={onClose} aria-label="Close flight history">
            <X size={16} />
          </button>
        </div>

        {sessions.length > 0 && (
          <label className="text-hud-xs text-hud-secondary mb-3">
            Session
            <select
              className="mt-1 w-full rounded-md border border-white/10 bg-black/70 px-3 py-2 text-sm text-white"
              value={selectedId}
              disabled={loadingEvents}
              onChange={(event) => setSelectedId(event.target.value)}
            >
              {sessions.map((session) => (
                <option key={session.id} value={session.id}>
                  {formatSession(session.started_at)} · {session.event_count} events · {session.status}
                </option>
              ))}
            </select>
          </label>
        )}

        {error && <p className="text-hud-xs text-danger mb-3" role="alert">{error}</p>}

        <div className="min-h-0 flex-1 overflow-y-auto rounded-lg border border-white/[0.06]">
          {loadingSessions && sessions.length === 0 ? (
            <p className="text-hud-xs text-hud-dim text-center py-8">Loading sessions…</p>
          ) : !selectedSession ? (
            <p className="text-hud-xs text-hud-dim text-center py-8">
              {error ? 'Flight history could not be loaded.' : 'No flight sessions recorded yet.'}
            </p>
          ) : loadingEvents && events.length === 0 ? (
            <p className="text-hud-xs text-hud-dim text-center py-8">Loading timeline…</p>
          ) : events.length === 0 ? (
            <p className="text-hud-xs text-hud-dim text-center py-8">No events recorded for this flight.</p>
          ) : (
            <ol className="divide-y divide-white/[0.06]">
              {events.map((event) => (
                <li key={event.id} className="flex items-start gap-3 px-3 py-2.5">
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
                </li>
              ))}
            </ol>
          )}
        </div>

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
      </section>
    </div>
  );
}
