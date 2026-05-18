/**
 * SnapshotModal — overlay modal showing snapshot detail.
 */

import { X, Camera, Clock, User, Smile } from 'lucide-react';
import type { Snapshot } from '@/store/cameraStore';

interface SnapshotModalProps {
  snapshot: Snapshot;
  onClose: () => void;
}

const EMOTION_LABEL: Record<string, string> = {
  happy: 'Senang',
  angry: 'Marah',
  neutral: 'Netral',
  sad: 'Sedih',
  fear: 'Takut',
};

export default function SnapshotModal({ snapshot, onClose }: SnapshotModalProps) {
  return (
    <div className="modal-overlay" onClick={onClose}>
      <div
        className="modal-card"
        onClick={(e) => e.stopPropagation()}
        id="snapshot-modal"
      >
        {/* Close button */}
        <button className="modal-card__close" onClick={onClose}>
          <X size={18} />
        </button>

        {/* Image */}
        <div className="modal-card__image-wrapper">
          <img
            src={snapshot.url}
            alt="Detected face"
            className="modal-card__image"
          />
        </div>

        {/* Details */}
        <div className="modal-card__details">
          <h3 className="modal-card__title">Detail Deteksi</h3>

          <div className="modal-card__row">
            <User size={14} />
            <span className="modal-card__label">Gender</span>
            <span className="modal-card__value">
              {snapshot.gender === 'male' ? 'Pria' : 'Wanita'}
            </span>
          </div>

          <div className="modal-card__row">
            <Smile size={14} />
            <span className="modal-card__label">Emosi</span>
            <span
              className="modal-card__value"
              style={{ color: emotionColor(snapshot.emotion) }}
            >
              {EMOTION_LABEL[snapshot.emotion] ?? snapshot.emotion}
            </span>
          </div>

          <div className="modal-card__row">
            <User size={14} />
            <span className="modal-card__label">Usia</span>
            <span className="modal-card__value">
              {snapshot.age} ({snapshot.age_group})
            </span>
          </div>

          <div className="modal-card__row">
            <Camera size={14} />
            <span className="modal-card__label">Kamera</span>
            <span className="modal-card__value">{snapshot.camera_name}</span>
          </div>

          <div className="modal-card__row">
            <Clock size={14} />
            <span className="modal-card__label">Waktu</span>
            <span className="modal-card__value">
              {formatTimestamp(snapshot.timestamp)}
            </span>
          </div>
        </div>
      </div>
    </div>
  );
}

function emotionColor(emotion: string): string {
  const map: Record<string, string> = {
    happy: '#22c55e',
    angry: '#ef4444',
    neutral: '#3b82f6',
    sad: '#a855f7',
    fear: '#eab308',
  };
  return map[emotion] ?? '#94a3b8';
}

function formatTimestamp(ts: string): string {
  try {
    return new Date(ts).toLocaleString('id-ID', {
      day: '2-digit',
      month: 'short',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
    });
  } catch {
    return ts;
  }
}
