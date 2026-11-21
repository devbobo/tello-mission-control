import { describe, it, expect, beforeEach } from 'vitest';
import { act, render, screen } from '@testing-library/react';
import ArtificialHorizon from '@/components/ArtificialHorizon';
import TelemetryPanel from '@/components/TelemetryPanel';
import { useDroneStore } from '@/stores/droneStore';

describe('TelemetryPanel', () => {
  beforeEach(() => {
    useDroneStore.setState({ telemetry: null });
  });

  it('shows dashes when telemetry is null', () => {
    render(<TelemetryPanel />);
    const dashes = screen.getAllByText('---');
    expect(dashes.length).toBeGreaterThanOrEqual(5);
    expect(screen.getByRole('img', { name: 'Artificial horizon: attitude unavailable' })).toBeInTheDocument();
    expect(screen.queryByTestId('horizon-attitude')).not.toBeInTheDocument();
  });

  it('displays supplied historical telemetry', () => {
    render(
      <TelemetryPanel
        telemetryOverride={{
          battery: 42,
          height: 75,
          flight_time: 9,
          temperature: { high: 65, low: 60 },
          attitude: { pitch: 1, roll: -2, yaw: 30 },
          speed: { x: 0, y: 0, z: 0 },
          barometer: 75,
          tof_distance: 75,
        }}
      />,
    );

    expect(screen.getByText('42%')).toBeInTheDocument();
    expect(screen.getByText('75 cm')).toBeInTheDocument();
    expect(screen.getByText('0:09')).toBeInTheDocument();
    expect(screen.getByRole('img', {
      name: 'Artificial horizon: pitch 1 degrees, roll -2 degrees',
    })).toBeInTheDocument();
    expect(screen.getByTestId('horizon-attitude')).toHaveAttribute(
      'transform', 'translate(60 61.1)',
    );
    expect(screen.getByTestId('horizon-aircraft')).toHaveAttribute('transform', 'rotate(-2 60 60)');
  });

  it('keeps the horizon level and rotates the aircraft as live attitude changes', () => {
    const telemetry = {
      battery: 85,
      height: 120,
      flight_time: 42,
      temperature: { high: 65, low: 60 },
      attitude: { pitch: 10, roll: 20, yaw: 180 },
      speed: { x: 0, y: 0, z: 0 },
      barometer: 120,
      tof_distance: 120,
    };
    useDroneStore.setState({ telemetry });
    render(<TelemetryPanel />);
    expect(screen.getByTestId('horizon-attitude')).toHaveAttribute(
      'transform', 'translate(60 71)',
    );
    expect(screen.getByTestId('horizon-aircraft')).toHaveAttribute('transform', 'rotate(20 60 60)');
    expect(screen.getByTestId('horizon-bank-scale')).toHaveAttribute('transform', 'rotate(20 60 60)');
    expect(screen.getByTestId('horizon-bank-pointer')).not.toHaveAttribute('transform');
    expect(screen.getByTestId('horizon-bank-pointer').parentElement?.getAttribute('transform')).not.toContain('rotate');

    act(() => useDroneStore.setState({
      telemetry: { ...telemetry, attitude: { pitch: -10, roll: -20, yaw: 180 } },
    }));
    expect(screen.getByTestId('horizon-attitude')).toHaveAttribute(
      'transform', 'translate(60 49)',
    );
    expect(screen.getByTestId('horizon-aircraft')).toHaveAttribute('transform', 'rotate(-20 60 60)');
    expect(screen.getByTestId('horizon-bank-scale')).toHaveAttribute('transform', 'rotate(-20 60 60)');
    expect(screen.getByTestId('horizon-bank-pointer')).not.toHaveAttribute('transform');
    expect(screen.getByTestId('horizon-bank-pointer').parentElement?.getAttribute('transform')).not.toContain('rotate');
    expect(screen.getByRole('img', {
      name: 'Artificial horizon: pitch -10 degrees, roll -20 degrees',
    })).toBeInTheDocument();
  });

  it('does not draw a level horizon for invalid attitude', () => {
    const telemetry = {
      battery: 85,
      height: 0,
      flight_time: 0,
      temperature: { high: 65, low: 60 },
      attitude: { pitch: NaN, roll: 0, yaw: 0 },
      speed: { x: 0, y: 0, z: 0 },
      barometer: 0,
      tof_distance: 0,
    };
    render(<TelemetryPanel telemetryOverride={telemetry} />);
    expect(screen.getByRole('img', { name: 'Artificial horizon: attitude unavailable' })).toBeInTheDocument();
    expect(screen.queryByTestId('horizon-attitude')).not.toBeInTheDocument();
  });

  it('keeps the horizon bounded at extreme pitch and shows inverted roll', () => {
    render(<ArtificialHorizon attitude={{ pitch: 120, roll: 180, yaw: 0 }} />);
    expect(screen.getByTestId('horizon-attitude')).toHaveAttribute(
      'transform', 'translate(60 159)',
    );
    expect(screen.getByTestId('horizon-aircraft')).toHaveAttribute('transform', 'rotate(180 60 60)');
  });

  it('shows the reported crash attitude with a level horizon and banked aircraft', () => {
    render(<ArtificialHorizon attitude={{ pitch: 2, roll: -63, yaw: 136 }} />);
    expect(screen.getByTestId('horizon-attitude')).toHaveAttribute(
      'transform', 'translate(60 62.2)',
    );
    expect(screen.getByTestId('horizon-aircraft')).toHaveAttribute('transform', 'rotate(-63 60 60)');
  });

  it('uses separate dial resources when live and replay indicators coexist', () => {
    render(
      <>
        <ArtificialHorizon attitude={{ pitch: 0, roll: 0, yaw: 0 }} />
        <ArtificialHorizon attitude={{ pitch: 10, roll: -20, yaw: 0 }} />
      </>,
    );
    const horizons = screen.getAllByTestId('horizon-attitude');
    const firstClip = horizons[0].parentElement?.getAttribute('clip-path');
    const secondClip = horizons[1].parentElement?.getAttribute('clip-path');
    expect(firstClip).toMatch(/^url\(#.+\)$/);
    expect(secondClip).toMatch(/^url\(#.+\)$/);
    expect(firstClip).not.toBe(secondClip);
  });

  it('shows battery percentage', () => {
    useDroneStore.setState({
      telemetry: {
        battery: 85,
        height: 120,
        flight_time: 42,
        temperature: { high: 65, low: 60 },
        attitude: { pitch: 2, roll: -1, yaw: 180 },
        speed: { x: 0, y: 10, z: 0 },
        barometer: 150.5,
        tof_distance: 120,
      },
    });
    render(<TelemetryPanel />);
    expect(screen.getByText('85%')).toBeInTheDocument();
  });

  it('shows altitude in cm', () => {
    useDroneStore.setState({
      telemetry: {
        battery: 50,
        height: 200,
        flight_time: 0,
        temperature: { high: 60, low: 55 },
        attitude: { pitch: 0, roll: 0, yaw: 0 },
        speed: { x: 0, y: 0, z: 0 },
        barometer: 0,
        tof_distance: 0,
      },
    });
    render(<TelemetryPanel />);
    expect(screen.getByText('200 cm')).toBeInTheDocument();
  });

  it('formats flight time as M:SS', () => {
    useDroneStore.setState({
      telemetry: {
        battery: 50,
        height: 0,
        flight_time: 125,
        temperature: { high: 60, low: 55 },
        attitude: { pitch: 0, roll: 0, yaw: 0 },
        speed: { x: 0, y: 0, z: 0 },
        barometer: 0,
        tof_distance: 0,
      },
    });
    render(<TelemetryPanel />);
    expect(screen.getByText('2:05')).toBeInTheDocument();
  });

  it('computes speed magnitude', () => {
    useDroneStore.setState({
      telemetry: {
        battery: 50,
        height: 0,
        flight_time: 0,
        temperature: { high: 60, low: 55 },
        attitude: { pitch: 0, roll: 0, yaw: 0 },
        speed: { x: 3, y: 4, z: 0 },
        barometer: 0,
        tof_distance: 0,
      },
    });
    render(<TelemetryPanel />);
    expect(screen.getByText('5 cm/s')).toBeInTheDocument();
  });
});
