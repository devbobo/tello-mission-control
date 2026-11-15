import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';
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

describe('FlightHistoryModal', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
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
});
