import { act, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import MarkerNavigationAssist from '@/components/MarkerNavigationAssist';
import { useDroneStore } from '@/stores/droneStore';

const arucoFrame = (timestamp: string) => ({
  data: {
    frame_id: 1,
    frame_width: 640,
    frame_height: 480,
    inference_ms: 8,
    aruco_dictionary: 'DICT_4X4_50',
    markers: [
      {
        marker_type: 'aruco' as const,
        marker_id: '7',
        payload: null,
        payload_truncated: false,
        x_min: 0.6,
        y_min: 0.1,
        x_max: 0.8,
        y_max: 0.4,
      },
    ],
  },
  timestamp,
});

describe('MarkerNavigationAssist', () => {
  afterEach(() => {
    vi.useRealTimers();
    act(() => {
      useDroneStore.setState({ markerFrame: null });
    });
  });

  it('draws detected marker bounds and provides manual centering guidance', () => {
    act(() => {
      useDroneStore.setState({ markerFrame: arucoFrame(new Date().toISOString()) });
    });

    render(<MarkerNavigationAssist />);

    expect(screen.getByText('1 marker detected')).toBeInTheDocument();
    const overlay = screen.getByRole('img', { name: 'QR and ArUco marker overlay' });
    expect(overlay).toHaveAttribute('viewBox', '0 0 640 480');
    expect(overlay.querySelector('rect')).toHaveAttribute('x', '384');
    expect(overlay.querySelector('rect')).toHaveAttribute('y', '48');

    fireEvent.click(screen.getByRole('button', { name: /ArUco #7/ }));
    expect(screen.getByText('above and right of frame center')).toBeInTheDocument();
    expect(
      screen.getByText(/Visual guidance only\. Align manually; no RC commands or autonomous movement\./),
    ).toBeInTheDocument();
  });

  it('shows QR payloads as text labels', () => {
    const baseFrame = arucoFrame(new Date().toISOString());
    const frame = {
      ...baseFrame,
      data: {
        ...baseFrame.data,
        markers: [
          {
            ...baseFrame.data.markers[0],
            marker_type: 'qr' as const,
            marker_id: '0123456789abcdef',
            payload: 'WAYPOINT-A',
          },
        ],
      },
    };
    act(() => {
      useDroneStore.setState({ markerFrame: frame });
    });

    render(<MarkerNavigationAssist />);

    expect(screen.getByRole('button', { name: /QR: WAYPOINT-A/ })).toBeInTheDocument();
  });

  it('hides stale marker overlays and indicates that video is unavailable', () => {
    vi.useFakeTimers();
    act(() => {
      useDroneStore.setState({
        markerFrame: arucoFrame(new Date(Date.now() - 10).toISOString()),
      });
    });

    const { queryByRole } = render(<MarkerNavigationAssist />);
    expect(queryByRole('img', { name: 'QR and ArUco marker overlay' })).toBeInTheDocument();

    act(() => {
      vi.advanceTimersByTime(1600);
    });

    expect(queryByRole('img', { name: 'QR and ArUco marker overlay' })).not.toBeInTheDocument();
    expect(screen.getByText('Waiting for video')).toBeInTheDocument();
  });
});
