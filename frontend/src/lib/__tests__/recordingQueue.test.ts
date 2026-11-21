import 'fake-indexeddb/auto';
import { waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { RecordingQueue, type QueuedRecording } from '@/lib/recordingQueue';

function recording(flightId: string): QueuedRecording {
  return {
    flightId,
    recordingId: `recording-${flightId}`,
    video: new Blob(['video'], { type: 'video/webm' }),
    startedAt: '2026-11-15T00:00:00Z',
    durationMs: 1000,
  };
}

describe('RecordingQueue', () => {
  it('restores a failed upload from IndexedDB and retries it after reopening', async () => {
    const databaseName = 'queue-restore-test';
    const failedUpload = vi.fn().mockRejectedValue(new Error('Offline'));
    const first = new RecordingQueue(databaseName, failedUpload);
    const video = await new Response('video', {
      headers: { 'Content-Type': 'video/webm' },
    }).blob();
    await first.enqueue({ ...recording('flight-restore'), video });
    await waitFor(() => expect(first.getSnapshot().failed).toHaveLength(1));
    expect(first.getSnapshot().failed[0].error).toBe('Offline');

    const retryUpload = vi.fn().mockResolvedValue(undefined);
    const restored = new RecordingQueue(databaseName, retryUpload);
    await restored.initialize();
    expect(restored.wasRecorded('flight-restore')).toBe(true);
    await waitFor(() => expect(retryUpload).toHaveBeenCalledOnce());
    await waitFor(() => expect(restored.getSnapshot().pending).toBe(0));
    expect(restored.getSnapshot().failed).toHaveLength(0);
    expect(retryUpload).toHaveBeenCalledWith(
      'flight-restore', expect.objectContaining({ size: 5, type: 'video/webm' }),
      '2026-11-15T00:00:00Z', 1000, 'recording-flight-restore',
    );
    const restoredVideo: Blob = retryUpload.mock.calls[0][1];
    expect(await restoredVideo.text()).toBe('video');
  });

  it('does not overwrite a queued recording for the same flight', async () => {
    const upload = vi.fn().mockRejectedValue(new Error('Offline'));
    const queue = new RecordingQueue('queue-duplicate-test', upload);
    await queue.enqueue(recording('flight-duplicate'));
    await waitFor(() => expect(queue.getSnapshot().failed).toHaveLength(1));
    await expect(queue.enqueue(recording('flight-duplicate'))).rejects.toThrow();
    expect(queue.getSnapshot().failed).toHaveLength(1);
  });

  it('retains a recording in memory when browser storage fails and permits a retry', async () => {
    const upload = vi.fn().mockResolvedValue(undefined);
    const queue = new RecordingQueue('queue-storage-failure-test', upload);
    const video = recording('flight-storage-failure');
    await queue.initialize();
    vi.spyOn(IDBObjectStore.prototype, 'add').mockImplementationOnce(() => {
      throw new Error('Storage full');
    });

    await expect(queue.enqueue(video)).rejects.toThrow('Storage full');
    expect(queue.pendingStorage).toBe(video);
    expect(queue.getSnapshot().ready).toBe(false);
    expect(queue.getSnapshot().error).toContain('Keep this page open and retry');

    await queue.enqueue(queue.pendingStorage!);
    expect(queue.pendingStorage).toBeNull();
    expect(queue.getSnapshot().ready).toBe(true);
    await waitFor(() => expect(upload).toHaveBeenCalledOnce());
  });
});
