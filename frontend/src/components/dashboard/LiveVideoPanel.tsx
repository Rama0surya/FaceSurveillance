/**
 * LiveVideoPanel — renders the video feed with bounding box overlays.
 *
 * - Displays base64 frames from WebSocket
 * - SVG overlay for face bounding boxes with emotion-based colors
 * - Timestamp overlay (top-left)
 * - Face counter (bottom-right)
 */

import { useMemo } from 'react';
import { useCameraStore } from '@/store/cameraStore';
import type { DetectionFace } from '@/store/cameraStore';
import { Video } from 'lucide-react';

/* Emotion → bbox color */
const BBOX_COLORS: Record<string, string> = {
  happy: '#22c55e',
  angry: '#ef4444',
  neutral: '#3b82f6',
  sad: '#a855f7',
  fear: '#eab308',
};

/* Emotion → label abbreviation */
const EMOTION_SHORT: Record<string, string> = {
  happy: 'Senang',
  angry: 'Marah',
  neutral: 'Netral',
  sad: 'Sedih',
  fear: 'Takut',
};

/* Assumed base frame resolution (adjust if backend sends different) */
const FRAME_W = 640;
const FRAME_H = 480;

export default function LiveVideoPanel() {
  const currentFrame = useCameraStore((s) => s.currentFrame);
  const currentFaces = useCameraStore((s) => s.currentFaces);
  const activeCamera = useCameraStore((s) => s.activeCamera);
  const isLive = useCameraStore((s) => s.isLive);

  const timestamp = useMemo(() => {
    return new Date().toLocaleString('en-GB', {
      day: '2-digit',
      month: '2-digit',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
    });
  }, [currentFaces]); // update when faces update

  return (
    <div className="live-panel" id="live-video-panel">
      <div className="live-panel__viewport">
        {/* Frame image */}
        {currentFrame ? (
          <img
            src={
              currentFrame.startsWith('data:')
                ? currentFrame
                : `data:image/jpeg;base64,${currentFrame}`
            }
            alt="Live feed"
            className="live-panel__frame"
            draggable={false}
          />
        ) : (
          <div className="live-panel__placeholder">
            <Video size={48} className="live-panel__placeholder-icon" />
            <span>
              {activeCamera
                ? isLive
                  ? 'Waiting for frame…'
                  : 'Connecting…'
                : 'Select a camera to begin'}
            </span>
          </div>
        )}

        {/* SVG overlay for bounding boxes */}
        {currentFrame && (
          <svg
            className="live-panel__overlay"
            viewBox={`0 0 ${FRAME_W} ${FRAME_H}`}
            preserveAspectRatio="none"
          >
            {currentFaces.map((face) => (
              <BoundingBox key={face.id} face={face} />
            ))}
          </svg>
        )}

        {/* Timestamp overlay — top-left */}
        <div className="live-panel__timestamp">{timestamp}</div>

        {/* Face counter — bottom-right */}
        <div className="live-panel__counter">
          <span className="live-panel__counter-dot" />
          {currentFaces.length} face{currentFaces.length !== 1 ? 's' : ''}
        </div>
      </div>
    </div>
  );
}

/* ---- Bounding Box sub-component ---- */
function BoundingBox({ face }: { face: DetectionFace }) {
  const color = BBOX_COLORS[face.emotion] ?? '#3b82f6';
  const label = `${face.gender === 'male' ? '♂' : '♀'} ${EMOTION_SHORT[face.emotion] ?? face.emotion}`;

  return (
    <g>
      <rect
        x={face.bbox.x}
        y={face.bbox.y}
        width={face.bbox.w}
        height={face.bbox.h}
        fill="none"
        stroke={color}
        strokeWidth={2}
        rx={2}
      />
      {/* Label background */}
      <rect
        x={face.bbox.x}
        y={face.bbox.y - 18}
        width={face.bbox.w}
        height={18}
        fill={color}
        rx={2}
        opacity={0.85}
      />
      {/* Label text */}
      <text
        x={face.bbox.x + 4}
        y={face.bbox.y - 5}
        fill="#fff"
        fontSize={11}
        fontWeight={600}
        fontFamily="Inter, sans-serif"
      >
        {label}
      </text>
    </g>
  );
}
