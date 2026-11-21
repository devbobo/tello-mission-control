import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { act, fireEvent, render, screen } from '@testing-library/react';
import FlightHistoryModal from '@/components/FlightHistoryModal';
import ConnectionScreen from '@/components/ConnectionScreen';
import * as api from '@/lib/api';
import type { FlightEvent, FlightSession } from '@/types/drone';

const session: FlightSession = {
  id: 'flight-1',
  started_at: '2026-11-15T00:00:00Z',
  ended_at: null,
  status: 'active',
  event_count: 2,
  video_available: false,
  video_started_at: null,
  video_duration_ms: null,
};

const commandEvent: FlightEvent = {
  id: 1,
  session_id: session.id,
  event_type: 'command',
  occurred_at: '2026-11-15T00:00:01Z',
  command: 'takeoff',
  params: {},
  result: 'ok',
  error: null,
  telemetry: null,
};

const telemetryEvent: FlightEvent = {
  id: 2,
  session_id: session.id,
  event_type: 'telemetry',
  occurred_at: '2026-11-15T00:00:02Z',
  command: null,
  params: {},
  result: null,
  error: null,
  telemetry: {
    battery: 80,
    height: 50,
    flight_time: 1,
    temperature: { high: 65, low: 60 },
    attitude: { pitch: 0, roll: 0, yaw: 0 },
    speed: { x: 0, y: 0, z: 0 },
    barometer: 50,
    tof_distance: 50,
  },
};

const moveEvent: FlightEvent = {
  ...commandEvent,
  id: 3,
  event_type: 'command',
  occurred_at: '2026-11-15T00:00:02.500Z',
  command: 'move',
  params: { direction: 'forward', distance_cm: 80 },
  result: 'error',
  error: 'Mock movement failure',
};

const landEvent: FlightEvent = {
  ...commandEvent,
  id: 4,
  occurred_at: '2026-11-15T00:00:03.500Z',
  command: 'land',
};

const recordingStartEvent: FlightEvent = {
  ...commandEvent,
  id: 5,
  occurred_at: '2026-11-15T00:00:02Z',
  command: 'recording_start',
};

const recordingStopEvent: FlightEvent = {
  ...commandEvent,
  id: 6,
  occurred_at: '2026-11-15T00:00:05Z',
  command: 'recording_stop',
};

const originalScrollIntoView = HTMLElement.prototype.scrollIntoView;

describe('FlightHistoryModal', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  afterEach(() => {
    vi.restoreAllMocks();
    if (originalScrollIntoView) {
      Object.defineProperty(HTMLElement.prototype, 'scrollIntoView', {
        configurable: true,
        value: originalScrollIntoView,
      });
    } else {
      Reflect.deleteProperty(HTMLElement.prototype, 'scrollIntoView');
    }
  });

  it('shows a read-only timeline and loads additional events', async () => {
    vi.spyOn(api, 'getFlightSessions').mockResolvedValue([session]);
    const eventsSpy = vi.spyOn(api, 'getFlightEvents')
      .mockResolvedValueOnce({
        items: [commandEvent],
        total: 2,
        limit: 1,
        offset: 0,
      })
      .mockResolvedValueOnce({
        items: [telemetryEvent],
        total: 2,
        limit: 1,
        offset: 1,
      });

    render(<FlightHistoryModal isOpen onClose={vi.fn()} />);

    expect(await screen.findByText('takeoff')).toBeInTheDocument();
    expect(screen.getByText('1 of 2 events · active')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Load more' }));

    expect(await screen.findByText(/Battery 80%/)).toBeInTheDocument();
    expect(eventsSpy).toHaveBeenLastCalledWith(session.id, 100, 1);
    expect(screen.getByText('2 of 2 events · active')).toBeInTheDocument();
  });

  it('can be opened from the disconnected connection screen', async () => {
    vi.spyOn(api, 'getFlightSessions').mockResolvedValue([]);

    render(<ConnectionScreen />);
    fireEvent.click(screen.getByRole('button', { name: /flight history/i }));

    expect(await screen.findByRole('dialog', { name: 'Flight history' })).toBeInTheDocument();
    expect(screen.getByText('No flight sessions recorded yet.')).toBeInTheDocument();
  });

  it('shows recording start and stop events in flight history', async () => {
    vi.spyOn(api, 'getFlightSessions').mockResolvedValue([session]);
    vi.spyOn(api, 'getFlightEvents').mockResolvedValue({
      items: [recordingStartEvent, recordingStopEvent],
      total: 2,
      limit: 100,
      offset: 0,
    });

    render(<FlightHistoryModal isOpen onClose={vi.fn()} />);

    expect(await screen.findByText('Recording started')).toBeInTheDocument();
    expect(screen.getByText('Recording stopped')).toBeInTheDocument();
  });

  it('updates telemetry with video playback and seeks from timeline events', async () => {
    const scrollIntoView = vi.fn();
    Object.defineProperty(HTMLElement.prototype, 'scrollIntoView', {
      configurable: true,
      value: scrollIntoView,
    });
    const recordedSession: FlightSession = {
      ...session,
      event_count: 4,
      video_available: true,
      video_started_at: '2026-11-15T00:00:00Z',
      video_duration_ms: 5000,
    };
    vi.spyOn(api, 'getFlightSessions').mockResolvedValue([recordedSession]);
    vi.spyOn(api, 'getFlightEvents').mockResolvedValue({
      items: [commandEvent, telemetryEvent, moveEvent],
      total: 4,
      limit: 100,
      offset: 0,
    });
    vi.spyOn(api, 'getAllFlightEvents').mockResolvedValue([
      commandEvent,
      telemetryEvent,
      moveEvent,
      landEvent,
    ]);

    const onClose = vi.fn();
    render(<FlightHistoryModal isOpen onClose={onClose} />);

    const video = await screen.findByLabelText('Flight recording') as HTMLVideoElement;
    expect(video.controls).toBe(false);
    expect(screen.getByRole('button', { name: 'Play flight recording' })).toBeInTheDocument();
    expect(screen.getByRole('slider', { name: 'Seek flight recording' })).toBeInTheDocument();
    Object.defineProperty(video, 'currentTime', { configurable: true, writable: true, value: 2 });
    video.play = vi.fn().mockResolvedValue(undefined);
    fireEvent.timeUpdate(video);

    expect(await screen.findByText(/BAT 80% · ALT 50 cm/)).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Enter full-screen replay' }));
    expect(screen.getByRole('dialog', { name: 'Full-screen flight replay' })).toBeInTheDocument();
    expect(screen.getByLabelText('Flight recording')).toBe(video);
    expect(screen.getByText('50 cm')).toBeInTheDocument();
    expect(screen.getByText('replay')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /seek to Battery 80%/i })).not.toBeInTheDocument();
    expect(screen.getByText('3 commands shown')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Load more' })).not.toBeInTheDocument();
    const takeoffTimelineItem = screen.getByRole('button', { name: /seek to takeoff/i });
    const moveTimelineItem = screen.getByRole('button', { name: /seek to move/i });
    expect(screen.getByRole('button', { name: /seek to land/i })).toBeInTheDocument();
    expect(takeoffTimelineItem).toHaveAttribute('data-replay-active', 'true');
    expect(moveTimelineItem).toHaveClass('opacity-40');
    expect(scrollIntoView).toHaveBeenCalledWith({
      block: 'nearest',
      inline: 'nearest',
      behavior: 'smooth',
    });
    expect(screen.getByRole('button', { name: 'Replay takeoff' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Replay takeoff' })).toHaveAttribute(
      'data-replay-active',
      'true',
    );
    expect(screen.getByRole('button', { name: 'Replay takeoff' })).toHaveClass('ring-info/80');
    expect(screen.getByRole('button', { name: 'Emergency Stop' })).toBeDisabled();

    Object.defineProperty(video, 'currentTime', { configurable: true, writable: true, value: 2.6 });
    fireEvent.timeUpdate(video);
    expect(screen.getByRole('button', { name: 'Move forward' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Move forward' })).toHaveAttribute(
      'data-replay-active',
      'true',
    );
    expect(screen.getByRole('button', { name: 'Move forward' })).toHaveClass('ring-danger/80');
    expect(moveTimelineItem).toHaveAttribute('data-replay-active', 'true');
    expect(takeoffTimelineItem).toHaveClass('opacity-40');

    fireEvent.click(screen.getByRole('button', { name: /seek to takeoff/i }));
    expect(video.currentTime).toBe(1);
    expect(video.play).toHaveBeenCalledOnce();
    fireEvent.timeUpdate(video);
    expect(screen.getByRole('button', { name: 'Replay takeoff' })).toHaveAttribute(
      'data-replay-active',
      'true',
    );
    expect(takeoffTimelineItem).toHaveAttribute('data-replay-active', 'true');

    video.pause = vi.fn();
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: 'Play flight recording' }));
      await Promise.resolve();
    });
    expect(screen.getByRole('button', { name: 'Pause flight recording' })).toBeInTheDocument();
    expect(video.play).toHaveBeenCalledTimes(2);
    fireEvent.click(screen.getByRole('button', { name: 'Pause flight recording' }));
    expect(video.pause).toHaveBeenCalledOnce();

    fireEvent.change(screen.getByRole('slider', { name: 'Seek flight recording' }), {
      target: { value: '4' },
    });
    expect(video.currentTime).toBe(4);

    fireEvent.keyDown(document, { key: 'Escape' });
    expect(screen.getByRole('dialog', { name: 'Flight history' })).toBeInTheDocument();
    expect(onClose).not.toHaveBeenCalled();
  });
});
