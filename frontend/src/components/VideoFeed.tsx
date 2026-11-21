import { Circle, Square } from 'lucide-react';
import { useCallback, useEffect, useRef, useState, useSyncExternalStore } from 'react';
import {
  closeWebRtcPeer,
  createWebRtcOffer,
  getActiveFlight,
  getWebRtcConfiguration,
  startNextFlightSession,
} from '@/lib/api';
import { recordingQueue } from '@/lib/recordingQueue';
import { useDroneStore } from '@/stores/droneStore';
import type { FlightSession } from '@/types/drone';

type FeedState = 'loading' | 'active' | 'error';
type RecordingState = 'idle' | 'recording' | 'finalizing' | 'saved' | 'error';

interface ActiveRecording {
  recorder: MediaRecorder;
  recordingId: string;
  flight: FlightSession;
  startedAt: string;
  startedAtMs: number;
  durationMs: number;
  chunks: Blob[];
  stopped: Promise<Blob>;
}

const MAX_RETRIES = 5;
const RETRY_DELAY_MS = 2000;
const ICE_GATHERING_TIMEOUT_MS = 10000;
const RECORDING_MIME_TYPES = [
  'video/webm;codecs=vp8',
  'video/webm;codecs=vp9',
  'video/webm',
];

function getRecordingMimeType(): string | null {
  if (typeof MediaRecorder === 'undefined') return null;
  return RECORDING_MIME_TYPES.find((type) => MediaRecorder.isTypeSupported(type)) ?? null;
}

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
  const connectionStatus = useDroneStore((s) => s.connectionStatus);
  const setRecordingReady = useDroneStore((s) => s.setRecordingReady);
  const setRecordingRequestHandler = useDroneStore((s) => s.setRecordingRequestHandler);
  const [state, setState] = useState<FeedState>('loading');
  const [activeFlight, setActiveFlight] = useState<FlightSession | null>(null);
  const [recordingState, setRecordingState] = useState<RecordingState>('idle');
  const [recordingError, setRecordingError] = useState('');
  const queue = useSyncExternalStore(recordingQueue.subscribe, recordingQueue.getSnapshot);
  const videoRef = useRef<HTMLVideoElement>(null);
  const recordingRef = useRef<ActiveRecording | null>(null);
  const finalizingRef = useRef(false);

  const stopRecording = useCallback(async (): Promise<boolean> => {
    const recording = recordingRef.current;
    if (!recording && !recordingQueue.pendingStorage) {
      setRecordingState('saved');
      return true;
    }
    if (finalizingRef.current) return false;
    finalizingRef.current = true;
    try {
      if (recording) {
        if (recording.recorder.state !== 'inactive') recording.recorder.stop();
        recordingRef.current = null;
        const video = await recording.stopped;
        await recordingQueue.enqueue({
          flightId: recording.flight.id,
          recordingId: recording.recordingId,
          video,
          startedAt: recording.startedAt,
          durationMs: recording.durationMs,
        });
      } else if (recordingQueue.pendingStorage) {
        await recordingQueue.enqueue(recordingQueue.pendingStorage);
      }
      setRecordingError('');
      setRecordingState('saved');
      return true;
    } catch (error) {
      setRecordingError(error instanceof Error ? error.message : 'Unable to finish flight recording');
      setRecordingState('error');
      return false;
    } finally {
      finalizingRef.current = false;
    }
  }, []);

  const startRecording = useCallback(async () => {
    if (recordingRef.current) return;
    if (finalizingRef.current || recordingQueue.pendingStorage) {
      throw new Error('The flight recording cannot be started in its current state');
    }

    try {
      await recordingQueue.initialize();
      let flight = await getActiveFlight();
      if (!flight) {
        throw new Error('There is no active flight available for recording');
      }
      if (flight.video_available || recordingQueue.wasRecorded(flight.id)) {
        flight = await startNextFlightSession(flight.id);
      }
      setActiveFlight(flight);
      const stream = videoRef.current?.srcObject;
      if (!(stream instanceof MediaStream)) {
        throw new Error('The live video feed is not ready yet');
      }

      const mimeType = getRecordingMimeType();
      if (!mimeType) {
        throw new Error('This browser does not support WebM video recording');
      }
      const recorder = new MediaRecorder(stream, { mimeType });
      const startedAtMs = Date.now();
      const chunks: Blob[] = [];
      let resolveStopped!: (video: Blob) => void;
      let rejectStopped!: (error: Error) => void;
      const stopped = new Promise<Blob>((resolve, reject) => {
        resolveStopped = resolve;
        rejectStopped = reject;
      });
      void stopped.catch(() => undefined);
      let resolveStarted!: () => void;
      let rejectStarted!: (error: Error) => void;
      const started = new Promise<void>((resolve, reject) => {
        resolveStarted = resolve;
        rejectStarted = reject;
      });
      const recording: ActiveRecording = {
        recorder,
        recordingId: Array.from(crypto.getRandomValues(new Uint8Array(16)), (byte) =>
          byte.toString(16).padStart(2, '0'),
        ).join(''),
        flight,
        startedAt: new Date(startedAtMs).toISOString(),
        startedAtMs,
        durationMs: 1,
        chunks,
        stopped,
      };
      recorder.ondataavailable = (event) => {
        if (event.data.size > 0) chunks.push(event.data);
      };
      recorder.onstart = () => resolveStarted();
      recorder.onerror = () => {
        const error = new Error('Browser video recording failed');
        rejectStopped(error);
        rejectStarted(error);
      };
      recorder.onstop = () => {
        recording.durationMs = Math.max(1, Date.now() - recording.startedAtMs);
        if (chunks.length === 0) {
          rejectStopped(new Error('No video data was captured'));
          return;
        }
        resolveStopped(new Blob(chunks, { type: recorder.mimeType || mimeType }));
      };
      recordingRef.current = recording;
      setRecordingError('');
      setRecordingState('recording');
      recorder.start(1000);
      await started;
    } catch (error) {
      const startError = error instanceof Error
        ? error
        : new Error('Unable to start video recording');
      if (recordingRef.current) recordingRef.current = null;
      setRecordingError(startError.message);
      setRecordingState('error');
      throw startError;
    }
  }, []);

  const toggleRecording = useCallback(async () => {
    if (recordingState === 'finalizing') return;
    if (recordingRef.current || recordingQueue.pendingStorage) {
      setRecordingState('finalizing');
      await stopRecording();
      return;
    }

    try {
      await startRecording();
    } catch {
      return;
    }
  }, [recordingState, startRecording, stopRecording]);

  useEffect(() => {
    if (!previewMode) void recordingQueue.initialize().catch(() => undefined);
  }, [previewMode]);

  useEffect(() => {
    if (previewMode) return;
    let cancelled = false;
    getActiveFlight().then(
      (flight) => {
        if (!cancelled) setActiveFlight(flight);
      },
      (error: unknown) => {
        if (!cancelled) {
          setRecordingError(error instanceof Error ? error.message : 'Unable to check flight session');
          setRecordingState('error');
        }
      },
    );
    return () => {
      cancelled = true;
    };
  }, [previewMode]);

  useEffect(() => {
    if (previewMode) return;
    const ready =
      connectionStatus === 'connected' &&
      state === 'active' &&
      activeFlight !== null &&
      queue.ready &&
      recordingState !== 'finalizing' &&
      !recordingQueue.pendingStorage &&
      getRecordingMimeType() !== null;
    setRecordingReady(ready);
    return () => setRecordingReady(false);
  }, [
    activeFlight,
    connectionStatus,
    previewMode,
    queue.ready,
    recordingState,
    setRecordingReady,
    state,
  ]);

  useEffect(() => {
    if (previewMode) return;
    setRecordingRequestHandler(async (action) => {
      if (action === 'start') {
        await startRecording();
        return;
      }

      setRecordingState('finalizing');
      if (!(await stopRecording())) {
        throw new Error('The browser could not finish the flight recording');
      }
    });
    return () => setRecordingRequestHandler(null);
  }, [
    previewMode,
    setRecordingRequestHandler,
    startRecording,
    stopRecording,
  ]);

  useEffect(() => {
    if (previewMode) return;

    let disposed = false;
    let retries = 0;
    let retryTimer: ReturnType<typeof setTimeout> | null = null;
    let retrying = false;
    let peer: RTCPeerConnection | null = null;
    let peerId: string | null = null;

    let connect: () => Promise<void>;

    const closeActivePeer = async () => {
      if (recordingRef.current) {
        setRecordingState('finalizing');
        await stopRecording();
      }
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
      void stopRecording().finally(() => {
        currentPeer?.close();
        if (videoRef.current) videoRef.current.srcObject = null;
        if (currentPeerId) {
          void closeWebRtcPeer(currentPeerId).catch((error: unknown) => {
            console.error('Failed to close WebRTC video peer:', error);
          });
        }
      });
    };
  }, [previewMode, stopRecording]);

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

      <div className="fixed top-3 left-1/2 z-[3] -translate-x-1/2 text-center">
        <button
          className={`control-btn px-3 py-2 text-hud-xs ${
            recordingState === 'recording'
              ? 'border-danger/60 text-danger'
              : 'text-white'
          }`}
          disabled={
            state !== 'active' ||
            recordingState === 'finalizing' ||
            (recordingState !== 'recording' && !activeFlight)
          }
          onClick={() => void toggleRecording()}
          aria-label={
            recordingState === 'recording'
              ? 'Stop flight recording'
              : recordingState === 'finalizing'
                ? 'Preparing flight video'
                : recordingQueue.pendingStorage
                  ? 'Retry preparing flight video'
                : recordingState === 'saved' || activeFlight?.video_available
                  ? 'Start next flight recording'
                  : 'Start flight recording'
          }
        >
          {recordingState === 'recording' ? <Square size={13} /> : <Circle size={13} />}
          {recordingState === 'recording'
            ? 'STOP RECORDING'
            : recordingState === 'finalizing'
              ? 'PREPARING VIDEO...'
              : recordingQueue.pendingStorage
                ? 'RETRY PREPARING VIDEO'
              : recordingState === 'saved' || activeFlight?.video_available
                ? 'RECORD NEXT FLIGHT'
                : 'RECORD FLIGHT'}
        </button>
        {recordingError && (
          <p className="mt-1 max-w-64 text-[10px] text-danger" role="alert">
            {recordingError}
          </p>
        )}
        {queue.pending > 0 && (
          <p className="mt-1 text-[10px] text-hud-dim" role="status">
            Saving {queue.pending} flight {queue.pending === 1 ? 'video' : 'videos'}...
          </p>
        )}
        {(queue.error || queue.failed.length > 0) && (
          <div className="mt-1 max-w-64 text-[10px] text-danger" role="alert">
            {queue.error ?? `${queue.failed.length} flight video(s) could not be saved: ${queue.failed[0].error}`}
            <button
              className="control-btn ml-2 p-1"
              onClick={() => {
                if (recordingQueue.pendingStorage) void stopRecording();
                else if (queue.error) void recordingQueue.initialize().catch(() => undefined);
                else recordingQueue.retryFailed();
              }}
            >
              Retry
            </button>
          </div>
        )}
      </div>

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
