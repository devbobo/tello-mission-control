import { act, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import PersonTrackingAssist from '@/components/PersonTrackingAssist';
import { useDroneStore } from '@/stores/droneStore';

function setVisionDetections(
  detections: Array<{
    label: string;
    confidence: number;
    x_min: number;
    y_min: number;
    x_max: number;
    y_max: number;
    track_id: number;
  }>,
) {
  act(() => {
    useDroneStore.setState({
      visionFrame: {
        data: {
          frame_id: 1,
          frame_width: 640,
          frame_height: 480,
          model: 'yolov8n',
          device: 'cpu',
          inference_ms: 20,
          detections,
        },
        timestamp: new Date().toISOString(),
      },
    });
  });
}

const person = {
  label: 'person',
  confidence: 0.9,
  x_min: 0.1,
  y_min: 0.2,
  x_max: 0.3,
  y_max: 0.4,
  track_id: 4,
};

describe('PersonTrackingAssist', () => {
  afterEach(() => {
    vi.useRealTimers();
    act(() => {
      useDroneStore.setState({ visionFrame: null });
    });
  });

  it('offers detected people for visual target selection only', () => {
    setVisionDetections([
      person,
      { ...person, label: 'car', track_id: 5 },
      { ...person, track_id: 6 },
    ]);
    const onSelectTrack = vi.fn();

    render(
      <PersonTrackingAssist
        selectedTrackId={null}
        onSelectTrack={onSelectTrack}
      />,
    );

    expect(screen.getByRole('button', { name: /Person #4/ })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Person #6/ })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Person #5/ })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: /Person #4/ }));
    expect(onSelectTrack).toHaveBeenCalledWith(4);
    expect(
      screen.getByText(/Flight controls remain manual; no RC commands are sent/),
    ).toBeInTheDocument();
  });

  it('shows manual centering guidance and lets the pilot clear a target', () => {
    setVisionDetections([person]);
    const onSelectTrack = vi.fn();

    render(
      <PersonTrackingAssist
        selectedTrackId={4}
        onSelectTrack={onSelectTrack}
      />,
    );

    expect(screen.getByText('above and left of center')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Clear target' }));
    expect(onSelectTrack).toHaveBeenCalledWith(null);
  });

  it('reports a selected target missing from the current frame', () => {
    setVisionDetections([]);

    render(
      <PersonTrackingAssist selectedTrackId={4} onSelectTrack={vi.fn()} />,
    );

    expect(screen.getByText('Target #4 — not in current frame')).toBeInTheDocument();
  });
});
