import { act, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import VisionOverlay from '@/components/VisionOverlay';
import { useDroneStore } from '@/stores/droneStore';

const visionFrame = (timestamp: string) => ({
  data: {
    frame_id: 7,
    frame_width: 640,
    frame_height: 480,
    model: 'yolov8n',
    device: 'cpu',
    inference_ms: 20,
    detections: [
      {
        label: 'person',
        confidence: 0.9,
        x_min: 0.1,
        y_min: 0.2,
        x_max: 0.5,
        y_max: 0.7,
      },
    ],
  },
  timestamp,
});

describe('VisionOverlay', () => {
  afterEach(() => {
    vi.useRealTimers();
    act(() => {
      useDroneStore.setState({ visionFrame: null });
    });
  });

  it('draws normalized boxes and labels in frame coordinates', () => {
    act(() => {
      useDroneStore.setState({ visionFrame: visionFrame(new Date().toISOString()) });
    });

    render(<VisionOverlay />);

    const overlay = screen.getByRole('img', { name: 'Object detection overlay' });
    expect(overlay).toHaveAttribute('viewBox', '0 0 640 480');
    expect(overlay).toHaveAttribute('preserveAspectRatio', 'xMidYMid slice');
    expect(overlay.querySelector('rect')).toHaveAttribute('x', '64');
    expect(overlay.querySelector('rect')).toHaveAttribute('y', '96');
    expect(overlay.querySelector('rect')).toHaveAttribute('width', '256');
    expect(Number(overlay.querySelector('rect')?.getAttribute('height'))).toBeCloseTo(240);
    expect(screen.getByText('person 90%')).toBeInTheDocument();
  });

  it('hides results after they become stale', () => {
    vi.useFakeTimers();
    act(() => {
      useDroneStore.setState({
        visionFrame: visionFrame(new Date(Date.now() - 10).toISOString()),
      });
    });

    const { queryByRole } = render(<VisionOverlay />);
    expect(queryByRole('img', { name: 'Object detection overlay' })).toBeInTheDocument();

    act(() => {
      vi.advanceTimersByTime(1500);
    });

    expect(queryByRole('img', { name: 'Object detection overlay' })).not.toBeInTheDocument();
  });

  it('does not render a frame whose timestamp is already stale', () => {
    act(() => {
      useDroneStore.setState({
        visionFrame: visionFrame(new Date(Date.now() - 2000).toISOString()),
      });
    });

    render(<VisionOverlay />);

    expect(screen.queryByTestId('vision-overlay')).not.toBeInTheDocument();
  });
});
