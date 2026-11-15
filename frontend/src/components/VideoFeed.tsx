import { useEffect, useRef, useState } from 'react';
import { closeWebRtcPeer, createWebRtcOffer, getWebRtcConfiguration } from '@/lib/api';
import { useDroneStore } from '@/stores/droneStore';
import PersonTrackingAssist from '@/components/PersonTrackingAssist';
import VisionOverlay from '@/components/VisionOverlay';

type FeedState = 'loading' | 'active' | 'error';

const MAX_RETRIES = 5;
const RETRY_DELAY_MS = 2000;
const ICE_GATHERING_TIMEOUT_MS = 10000;

function waitForIceGatheringComplete(peer: RTCPeerConnection): Promise<void> {
  if (peer.iceGatheringState === 'complete') return Promise.resolve();

  return new Promise((resolve, reject) => {
    const cleanup = () => {
      peer.removeEventListener('icegatheringstatechange', handleStateChange);
      clearTimeout(timeout);
    };
    const handleStateChange = () => {
      if (peer.iceGatheringState === 'complete') {
        cleanup();
        resolve();
      }
    };
    const timeout = setTimeout(() => {
      cleanup();
      reject(new Error('Timed out gathering WebRTC connection candidates'));
    }, ICE_GATHERING_TIMEOUT_MS);

    peer.addEventListener('icegatheringstatechange', handleStateChange);
    handleStateChange();
  });
}

export default function VideoFeed() {
  const previewMode = useDroneStore((s) => s.previewMode);
  const [state, setState] = useState<FeedState>('loading');
  const [selectedTrackId, setSelectedTrackId] = useState<number | null>(null);
  const videoRef = useRef<HTMLVideoElement>(null);

  useEffect(() => {
    if (previewMode) {
      setSelectedTrackId(null);
      return;
    }

    let disposed = false;
    let retries = 0;
    let retryTimer: ReturnType<typeof setTimeout> | null = null;
    let retrying = false;
    let peer: RTCPeerConnection | null = null;
    let peerId: string | null = null;

    let connect: () => Promise<void>;

    const closeActivePeer = async () => {
      const currentPeer = peer;
      const currentPeerId = peerId;
      peer = null;
      peerId = null;
      currentPeer?.close();
      if (videoRef.current) videoRef.current.srcObject = null;
      if (currentPeerId) {
        try {
          await closeWebRtcPeer(currentPeerId);
        } catch (error) {
          console.error('Failed to close WebRTC video peer:', error);
        }
      }
    };

    const retry = async () => {
      if (disposed || retrying) return;
      retrying = true;
      await closeActivePeer();
      if (disposed) return;
      if (retries >= MAX_RETRIES) {
        setState('error');
        return;
      }
      setState('loading');
      retryTimer = setTimeout(() => {
        retries += 1;
        retrying = false;
        void connect();
      }, RETRY_DELAY_MS);
    };

    connect = async () => {
      if (disposed) return;
      setState('loading');
      try {
        const configuration = await getWebRtcConfiguration();
        if (disposed) return;
        const connection = new RTCPeerConnection(configuration);
        peer = connection;
        connection.addTransceiver('video', { direction: 'recvonly' });
        connection.ontrack = (event) => {
          if (disposed || !videoRef.current) return;
          videoRef.current.srcObject =
            event.streams[0] ?? new MediaStream([event.track]);
          void videoRef.current.play().catch(() => retry());
        };
        connection.onconnectionstatechange = () => {
          if (connection.connectionState === 'failed') void retry();
        };

        const offer = await connection.createOffer();
        await connection.setLocalDescription(offer);
        await waitForIceGatheringComplete(connection);
        if (disposed) return;
        const localDescription = connection.localDescription;
        if (!localDescription?.sdp) throw new Error('WebRTC offer was not created');

        const answer = await createWebRtcOffer(localDescription.sdp);
        peerId = answer.peer_id;
        if (disposed) {
          await closeActivePeer();
          return;
        }
        await connection.setRemoteDescription({
          sdp: answer.sdp,
          type: answer.type,
        });
      } catch {
        await retry();
      }
    };

    void connect();

    return () => {
      disposed = true;
      if (retryTimer) clearTimeout(retryTimer);
      const currentPeer = peer;
      const currentPeerId = peerId;
      peer = null;
      peerId = null;
      currentPeer?.close();
      if (videoRef.current) videoRef.current.srcObject = null;
      if (currentPeerId) {
        void closeWebRtcPeer(currentPeerId).catch((error: unknown) => {
          console.error('Failed to close WebRTC video peer:', error);
        });
      }
    };
  }, [previewMode]);

  if (previewMode) {
    return (
      <div className="fixed inset-0 z-0 flex items-center justify-center bg-[#0A0A0A]">
        <div
          className="absolute inset-0 opacity-[0.03]"
          style={{
            backgroundImage:
              'linear-gradient(rgba(255,255,255,0.1) 1px, transparent 1px), linear-gradient(90deg, rgba(255,255,255,0.1) 1px, transparent 1px)',
            backgroundSize: '40px 40px',
          }}
        />
        <span className="text-hud-sm font-mono uppercase tracking-[0.08em] text-hud-dim">
          No Video — Preview Mode
        </span>
      </div>
    );
  }

  return (
    <>
      <video
        ref={videoRef}
        autoPlay
        muted
        playsInline
        aria-label="Tello video feed"
        className="fixed inset-0 z-0 h-full w-full bg-black object-contain"
        onPlaying={() => setState('active')}
      />

      {state === 'active' && (
        <>
          <VisionOverlay selectedTrackId={selectedTrackId} />
          <PersonTrackingAssist
            selectedTrackId={selectedTrackId}
            onSelectTrack={setSelectedTrackId}
          />
        </>
      )}

      {state === 'loading' && (
        <div className="fixed inset-0 z-0 flex items-center justify-center bg-black">
          <div className="h-3 w-3 animate-pulse rounded-full bg-white/60" />
        </div>
      )}

      {state === 'error' && (
        <div className="fixed inset-0 z-0 flex items-center justify-center bg-[#0A0A0A]">
          <span className="text-hud-sm font-mono uppercase tracking-[0.08em] text-hud-dim">
            Video Feed Unavailable
          </span>
        </div>
      )}
    </>
  );
}
