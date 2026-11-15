import { act, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import VisualOdometryMap from '@/components/VisualOdometryMap';
import { useDroneStore } from '@/stores/droneStore';

describe('VisualOdometryMap', () => {
  afterEach(() => {
    vi.useRealTimers();
    act(() => {
      useDroneStore.setState({ odometryFrame: null });
    });
  });

  it('shows the relative trail and tracking quality', async () => {
    act(() => {
      useDroneStore.setState({
        odometryFrame: {
          data: {
            frame_id: 1,
            frame_width: 640,
            frame_height: 480,
            position_x: 0.02,
            position_y: -0.01,
            delta_x: 0.02,
            delta_y: -0.01,
            tracking_valid: true,
            tracked_points: 16,
            quality: 0.75,
          },
          timestamp: new Date().toISOString(),
        },
      });
    });

    render(<VisualOdometryMap />);

    expect(
      screen.getByRole('region', { name: 'Visual odometry minimap' }),
    ).toBeInTheDocument();
    expect(screen.getByText('FLOW LOCKED')).toBeInTheDocument();
    expect(screen.getByText('75%')).toBeInTheDocument();
    expect(screen.getByText('X 0.020 / Y -0.010')).toBeInTheDocument();
    expect(screen.getByText('Relative image units, not meters or GPS.')).toBeInTheDocument();
    expect(screen.getByRole('img', { name: 'Relative image-space movement map' })).toBeInTheDocument();
  });

  it('does not imply a position when no fresh estimate is available', () => {
    render(<VisualOdometryMap />);

    expect(screen.getByText('WAITING')).toBeInTheDocument();
    expect(screen.getByText('X 0.000 / Y 0.000')).toBeInTheDocument();
  });

  it('marks an estimate as waiting when it becomes stale', () => {
    vi.useFakeTimers();
    act(() => {
      useDroneStore.setState({
        odometryFrame: {
          data: {
            frame_id: 1,
            frame_width: 640,
            frame_height: 480,
            position_x: 0.02,
            position_y: -0.01,
            delta_x: 0.02,
            delta_y: -0.01,
            tracking_valid: true,
            tracked_points: 16,
            quality: 0.75,
          },
          timestamp: new Date().toISOString(),
        },
      });
    });

    render(<VisualOdometryMap />);
    expect(screen.getByText('FLOW LOCKED')).toBeInTheDocument();

    act(() => {
      vi.advanceTimersByTime(1600);
    });

    expect(screen.getByText('WAITING')).toBeInTheDocument();
  });
});
