import { uploadFlightVideo } from '@/lib/api';

export interface QueuedRecording {
  flightId: string;
  recordingId: string;
  video: Blob;
  startedAt: string;
  durationMs: number;
}

interface QueueItem {
  recording: QueuedRecording;
  status: 'queued' | 'saving' | 'failed';
  error?: string;
}

interface QueueSnapshot {
  ready: boolean;
  pending: number;
  failed: { flightId: string; error: string }[];
  error: string | null;
}

type Upload = (flightId: string, video: Blob, startedAt: string, durationMs: number, recordingId: string) => Promise<void>;

export class RecordingQueue {
  private database: IDBDatabase | null = null;
  private initializing: Promise<void> | null = null;
  private items: QueueItem[] = [];
  private recordedIds = new Set<string>();
  private listeners = new Set<() => void>();
  private processing = false;
  private unstoredRecording: QueuedRecording | null = null;
  private storageError: string | null = null;
  private snapshot: QueueSnapshot = { ready: false, pending: 0, failed: [], error: null };

  constructor(
    private readonly databaseName = 'tello-recording-queue',
    private readonly upload: Upload = (...args) => uploadFlightVideo(...args),
  ) {}

  subscribe = (listener: () => void) => {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  };

  getSnapshot = () => this.snapshot;

  async initialize(): Promise<void> {
    if (this.initializing) return this.initializing;
    if (this.database) return;
    this.initializing = this.open().then(async (database) => {
      this.database = database;
      try {
        const recordings = await this.readAll();
        this.items = recordings.map((recording) => ({ recording, status: 'queued' }));
        recordings.forEach((recording) => this.recordedIds.add(recording.flightId));
        this.update(true, null);
        void this.process();
      } catch (error) {
        database.close();
        this.database = null;
        throw error;
      }
    }).catch((error: unknown) => {
      const message = error instanceof Error ? error.message : 'Unable to open recording queue';
      this.update(false, message);
      throw new Error(message);
    }).finally(() => {
      this.initializing = null;
    });
    return this.initializing;
  }

  wasRecorded(flightId: string): boolean {
    return this.recordedIds.has(flightId);
  }

  get pendingStorage(): QueuedRecording | null {
    return this.unstoredRecording;
  }

  async enqueue(recording: QueuedRecording): Promise<void> {
    if (this.unstoredRecording && this.unstoredRecording !== recording) {
      throw new Error('Another recording is waiting for browser storage');
    }
    this.unstoredRecording = recording;
    try {
      await this.initialize();
      await this.write('add', recording);
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Unable to store flight recording';
      this.storageError = `Recording is not stored in the browser: ${message}. Keep this page open and retry.`;
      this.update(false, this.storageError);
      throw error;
    }
    this.unstoredRecording = null;
    this.storageError = null;
    this.recordedIds.add(recording.flightId);
    this.items.push({ recording, status: 'queued' });
    this.update(true, null);
    void this.process();
  }

  retryFailed(): void {
    for (const item of this.items) {
      if (item.status === 'failed') {
        item.status = 'queued';
        delete item.error;
      }
    }
    this.update(true, null);
    void this.process();
  }

  private async process(): Promise<void> {
    if (this.processing) return;
    this.processing = true;
    try {
      let item = this.items.find((candidate) => candidate.status === 'queued');
      while (item) {
        item.status = 'saving';
        this.update(true, null);
        try {
          const { flightId, video, startedAt, durationMs, recordingId } = item.recording;
          await this.upload(flightId, video, startedAt, durationMs, recordingId);
          await this.write('delete', flightId);
          this.items = this.items.filter((candidate) => candidate !== item);
        } catch (error) {
          item.status = 'failed';
          item.error = error instanceof Error ? error.message : 'Unable to save flight video';
        }
        this.update(true, null);
        item = this.items.find((candidate) => candidate.status === 'queued');
      }
    } finally {
      this.processing = false;
    }
  }

  private update(ready: boolean, error: string | null): void {
    this.snapshot = {
      ready: ready && this.unstoredRecording === null,
      pending: this.items.filter((item) => item.status !== 'failed').length,
      failed: this.items.filter((item) => item.status === 'failed').map((item) => ({
        flightId: item.recording.flightId,
        error: item.error ?? 'Unable to save flight video',
      })),
      error: this.storageError ?? error,
    };
    this.listeners.forEach((listener) => listener());
  }

  private open(): Promise<IDBDatabase> {
    return new Promise((resolve, reject) => {
      const request = indexedDB.open(this.databaseName, 1);
      request.onupgradeneeded = () => request.result.createObjectStore('recordings', { keyPath: 'flightId' });
      request.onsuccess = () => resolve(request.result);
      request.onerror = () => reject(request.error ?? new Error('Unable to open recording queue'));
      request.onblocked = () => reject(new Error('Recording queue is blocked by another browser tab'));
    });
  }

  private readAll(): Promise<QueuedRecording[]> {
    return new Promise((resolve, reject) => {
      if (!this.database) {
        reject(new Error('Recording queue is unavailable'));
        return;
      }
      const transaction = this.database.transaction('recordings', 'readonly');
      const request = transaction.objectStore('recordings').getAll();
      transaction.oncomplete = () => resolve(request.result as QueuedRecording[]);
      transaction.onerror = () => reject(transaction.error ?? new Error('Unable to read recording queue'));
      transaction.onabort = () => reject(transaction.error ?? new Error('Unable to read recording queue'));
    });
  }

  private write(action: 'add' | 'delete', value: QueuedRecording | string): Promise<void> {
    return new Promise((resolve, reject) => {
      if (!this.database) {
        reject(new Error('Recording queue is unavailable'));
        return;
      }
      const transaction = this.database.transaction('recordings', 'readwrite');
      const store = transaction.objectStore('recordings');
      if (action === 'add' && typeof value !== 'string') store.add(value);
      else if (action === 'delete' && typeof value === 'string') store.delete(value);
      else throw new Error('Invalid recording queue operation');
      transaction.oncomplete = () => resolve();
      transaction.onerror = () => reject(transaction.error ?? new Error('Unable to update recording queue'));
      transaction.onabort = () => reject(transaction.error ?? new Error('Unable to update recording queue'));
    });
  }
}

export const recordingQueue = new RecordingQueue();
