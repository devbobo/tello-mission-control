import { render, waitFor } from '@testing-library/react';
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
});
