import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import * as api from '@/lib/api';
import VideoFeed from '@/components/VideoFeed';
import { useDroneStore } from '@/stores/droneStore';

class MockPeerConnection {
  iceGatheringState = 'complete';
  connectionState = 'new';
  localDescription: RTCSessionDescriptionInit | null = null;
  ontrack: ((event: RTCTrackEvent) => void) | null = null;
  onconnectionstatechange: (() => void) | null = null;
  addTransceiver = vi.fn();
  addEventListener = vi.fn();
  removeEventListener = vi.fn();
  close = vi.fn();
  createOffer = vi.fn().mockResolvedValue({ sdp: 'offer-sdp', type: 'offer' });
  setLocalDescription = vi.fn(async (description: RTCSessionDescriptionInit) => {
    this.localDescription = description;
  });
  setRemoteDescription = vi.fn().mockResolvedValue(undefined);
}

describe('VideoFeed', () => {
  afterEach(() => {
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  it('negotiates a WebRTC video peer and closes it on unmount', async () => {
    const connection = new MockPeerConnection();
    vi.stubGlobal('RTCPeerConnection', vi.fn(() => connection));
    const createOffer = vi.spyOn(api, 'createWebRtcOffer').mockResolvedValue({
      sdp: 'answer-sdp',
      type: 'answer',
      peer_id: 'peer-1',
    });
    vi.spyOn(api, 'getWebRtcConfiguration').mockResolvedValue({ iceServers: [] });
    vi.spyOn(api, 'getActiveFlight').mockResolvedValue({
      id: 'flight-1',
      started_at: '2026-11-15T00:00:00Z',
      ended_at: null,
      status: 'active',
      event_count: 1,
      video_available: false,
      video_started_at: null,
      video_duration_ms: null,
    });
    const closePeer = vi.spyOn(api, 'closeWebRtcPeer').mockResolvedValue();
    useDroneStore.setState({ previewMode: false });

    const { unmount } = render(<VideoFeed />);
    await waitFor(() => expect(connection.setRemoteDescription).toHaveBeenCalledWith({
      sdp: 'answer-sdp',
      type: 'answer',
    }));
    expect(createOffer).toHaveBeenCalledWith('offer-sdp');
    expect(connection.addTransceiver).toHaveBeenCalledWith('video', { direction: 'recvonly' });

    unmount();
    await waitFor(() => expect(closePeer).toHaveBeenCalledWith('peer-1'));
    expect(connection.close).toHaveBeenCalledOnce();
  });

  it('records the live stream and saves it to the active flight', async () => {
    class MockMediaRecorder {
      static isTypeSupported = vi.fn(() => true);
      state = 'inactive';
      mimeType: string;
      ondataavailable: ((event: BlobEvent) => void) | null = null;
      onstart: (() => void) | null = null;
      onerror: (() => void) | null = null;
      onstop: (() => void) | null = null;

      constructor(_stream: MediaStream, options: MediaRecorderOptions) {
        this.mimeType = options.mimeType ?? 'video/webm';
      }

      start = vi.fn(() => {
        this.state = 'recording';
        this.onstart?.();
      });

      stop = vi.fn(() => {
        this.state = 'inactive';
        this.ondataavailable?.({ data: new Blob(['recording']) } as BlobEvent);
        this.onstop?.();
      });
    }

    const connection = new MockPeerConnection();
    vi.stubGlobal('RTCPeerConnection', vi.fn(() => connection));
    vi.stubGlobal('MediaStream', class {});
    vi.stubGlobal('MediaRecorder', MockMediaRecorder);
    vi.spyOn(HTMLMediaElement.prototype, 'play').mockResolvedValue();
    vi.spyOn(api, 'createWebRtcOffer').mockResolvedValue({
      sdp: 'answer-sdp',
      type: 'answer',
      peer_id: 'peer-1',
    });
    vi.spyOn(api, 'getWebRtcConfiguration').mockResolvedValue({ iceServers: [] });
    const closePeer = vi.spyOn(api, 'closeWebRtcPeer').mockResolvedValue();
    vi.spyOn(api, 'getActiveFlight').mockResolvedValue({
      id: 'flight-1',
      started_at: '2026-11-15T00:00:00Z',
      ended_at: null,
      status: 'active',
      event_count: 1,
      video_available: false,
      video_started_at: null,
      video_duration_ms: null,
    });
    const uploadVideo = vi.spyOn(api, 'uploadFlightVideo').mockResolvedValue();
    useDroneStore.setState({ previewMode: false });

    const { unmount } = render(<VideoFeed />);
    await waitFor(() => expect(connection.setRemoteDescription).toHaveBeenCalled());
    const stream = new MediaStream();
    connection.ontrack?.({ streams: [stream] } as unknown as RTCTrackEvent);
    const video = screen.getByLabelText('Tello video feed');
    fireEvent.playing(video);

    await waitFor(() =>
      expect(screen.getByRole('button', { name: 'Start flight recording' })).toBeEnabled(),
    );
    fireEvent.click(screen.getByRole('button', { name: 'Start flight recording' }));
    fireEvent.click(screen.getByRole('button', { name: 'Stop flight recording' }));

    await waitFor(() => expect(uploadVideo).toHaveBeenCalledWith(
      'flight-1',
      expect.any(Blob),
      expect.any(String),
      expect.any(Number),
    ));
    expect(await screen.findByRole('button', { name: 'Flight video saved' })).toHaveTextContent(
      'VIDEO SAVED',
    );
    unmount();
    await waitFor(() => expect(closePeer).toHaveBeenCalledWith('peer-1'));
  });

  it('handles backend requests to start and stop the browser recorder', async () => {
    class MockMediaRecorder {
      static isTypeSupported = vi.fn(() => true);
      state = 'inactive';
      mimeType: string;
      ondataavailable: ((event: BlobEvent) => void) | null = null;
      onstart: (() => void) | null = null;
      onerror: (() => void) | null = null;
      onstop: (() => void) | null = null;

      constructor(_stream: MediaStream, options: MediaRecorderOptions) {
        this.mimeType = options.mimeType ?? 'video/webm';
      }

      start = vi.fn(() => {
        this.state = 'recording';
        this.onstart?.();
      });

      stop = vi.fn(() => {
        this.state = 'inactive';
        this.ondataavailable?.({ data: new Blob(['recording']) } as BlobEvent);
        this.onstop?.();
      });
    }

    const connection = new MockPeerConnection();
    vi.stubGlobal('RTCPeerConnection', vi.fn(() => connection));
    vi.stubGlobal('MediaStream', class {});
    vi.stubGlobal('MediaRecorder', MockMediaRecorder);
    vi.spyOn(HTMLMediaElement.prototype, 'play').mockResolvedValue();
    vi.spyOn(api, 'createWebRtcOffer').mockResolvedValue({
      sdp: 'answer-sdp',
      type: 'answer',
      peer_id: 'peer-1',
    });
    vi.spyOn(api, 'getWebRtcConfiguration').mockResolvedValue({ iceServers: [] });
    vi.spyOn(api, 'closeWebRtcPeer').mockResolvedValue();
    vi.spyOn(api, 'getActiveFlight').mockResolvedValue({
      id: 'flight-1',
      started_at: '2026-11-15T00:00:00Z',
      ended_at: null,
      status: 'active',
      event_count: 1,
      video_available: false,
      video_started_at: null,
      video_duration_ms: null,
    });
    const uploadVideo = vi.spyOn(api, 'uploadFlightVideo').mockResolvedValue();
    useDroneStore.setState({
      previewMode: false,
      connectionStatus: 'connected',
      recordingReady: false,
      recordingRequestHandler: null,
    });

    const { unmount } = render(<VideoFeed />);
    await waitFor(() => expect(connection.setRemoteDescription).toHaveBeenCalled());
    connection.ontrack?.({ streams: [new MediaStream()] } as unknown as RTCTrackEvent);
    fireEvent.playing(screen.getByLabelText('Tello video feed'));
    await waitFor(() => expect(useDroneStore.getState().recordingReady).toBe(true));

    const requestHandler = useDroneStore.getState().recordingRequestHandler;
    expect(requestHandler).not.toBeNull();
    await act(async () => {
      await requestHandler?.('start');
    });
    expect(screen.getByRole('button', { name: 'Stop flight recording' })).toBeInTheDocument();

    await act(async () => {
      await requestHandler?.('stop');
    });
    await waitFor(() => expect(uploadVideo).toHaveBeenCalled());
    unmount();
  });
});
