import { useFreshVisionFrame } from '@/hooks/useFreshVisionFrame';
import type { VisionDetection } from '@/types/drone';

interface PersonTrackingAssistProps {
  selectedTrackId: number | null;
  onSelectTrack: (trackId: number | null) => void;
}

function hasTrackId(
  detection: VisionDetection,
): detection is VisionDetection & { track_id: number } {
  return typeof detection.track_id === 'number';
}

function targetPosition(detection: VisionDetection): string {
  const centerX = (detection.x_min + detection.x_max) / 2;
  const centerY = (detection.y_min + detection.y_max) / 2;
  const horizontal =
    Math.abs(centerX - 0.5) < 0.08
      ? null
      : centerX < 0.5
        ? 'left'
        : 'right';
  const vertical =
    Math.abs(centerY - 0.5) < 0.08
      ? null
      : centerY < 0.5
        ? 'above'
        : 'below';
  const offset = [vertical, horizontal].filter(Boolean).join(' and ');

  return offset ? `${offset} of center` : 'near frame center';
}

export default function PersonTrackingAssist({
  selectedTrackId,
  onSelectTrack,
}: PersonTrackingAssistProps) {
  const visionFrame = useFreshVisionFrame();
  const people =
    visionFrame?.data.detections.filter(
      (detection): detection is VisionDetection & { track_id: number } =>
        detection.label.toLowerCase() === 'person' &&
        hasTrackId(detection),
    ) ?? [];
  const selectedPerson = people.find(
    (person) => person.track_id === selectedTrackId,
  );

  if (people.length === 0 && selectedTrackId === null) return null;

  return (
    <section
      aria-label="Person tracking assistance"
      className="fixed bottom-20 right-3 z-[2] w-[min(90vw,260px)] hud-panel !p-3 pointer-events-auto"
    >
      <h2 className="hud-label mb-2 text-white">Person Tracking Assist</h2>
      {selectedTrackId !== null && (
        <div className="mb-2 rounded border border-sky-300/20 bg-sky-300/10 px-2 py-1.5">
          <div className="text-xs font-semibold text-sky-200">
            Target #{selectedTrackId}
            {selectedPerson ? '' : ' — not in current frame'}
          </div>
          {selectedPerson && (
            <div className="mt-0.5 text-[11px] text-white/70">
              {targetPosition(selectedPerson)}
            </div>
          )}
        </div>
      )}

      {people.length > 0 ? (
        <div className="max-h-[20vh] space-y-1 overflow-y-auto">
          {people.slice(0, 4).map((person) => {
            const trackId = person.track_id;
            const isSelected = trackId === selectedTrackId;
            return (
              <button
                key={trackId}
                type="button"
                aria-pressed={isSelected}
                className="control-btn w-full !justify-between px-2 py-1.5 text-left text-xs"
                onClick={() =>
                  onSelectTrack(isSelected ? null : trackId)
                }
              >
                <span>Person #{trackId}</span>
                <span className="text-white/60">
                  {Math.round(person.confidence * 100)}%
                </span>
              </button>
            );
          })}
        </div>
      ) : (
        selectedTrackId !== null && (
          <p className="text-xs text-white/60">No current person detection.</p>
        )
      )}

      {selectedTrackId !== null && (
        <button
          type="button"
          className="mt-2 w-full text-left text-[11px] text-sky-200 underline underline-offset-2"
          onClick={() => onSelectTrack(null)}
        >
          Clear target
        </button>
      )}
      <p className="mt-2 border-t border-white/10 pt-2 text-[10px] leading-relaxed text-white/50">
        Visual guidance only. Flight controls remain manual; no RC commands are sent.
      </p>
    </section>
  );
}
