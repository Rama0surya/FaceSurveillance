/**
 * CameraCard — card component for camera list with persistent stream preview.
 *
 * Stream preview uses the same ref-based pattern as LiveVideoPanel:
 * the <img> element is never unmounted by React.  Its src is changed
 * imperatively, so the MJPEG connection only drops when the camera
 * goes offline (not on re-renders).
 */

import React, { useState, useEffect, useRef, useCallback } from 'react';
import {
  Play,
  Square,
  Pencil,
  Trash2,
  Crosshair,
  Video,
  Wifi,
  WifiOff,
  Loader2,
} from 'lucide-react';
import type { Camera, ZonePoint } from '@/store/cameraStore';
import AddCameraModal from './AddCameraModal';
import DetectionZoneEditor from './DetectionZoneEditor';

const API_BASE = import.meta.env.VITE_API_URL ?? 'http://localhost:8000';

// Hard cap on retry attempts to prevent log spam
const MAX_PREVIEW_RETRIES = 10;

interface Props {
  camera: Camera;
  zonePoints: ZonePoint[];
  onUpdate: (id: string, patch: { name?: string; rtsp_url?: string }) => void;
  onDelete: (id: string) => void;
  onStatusChange: (id: string, status: Camera['status']) => void;
  onSaveZone: (id: string, points: ZonePoint[]) => void;
}

function CameraCard({
  camera,
  zonePoints,
  onUpdate,
  onDelete,
  onStatusChange,
  onSaveZone,
}: Props) {
  const [editOpen, setEditOpen] = useState(false);
  const [zoneOpen, setZoneOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [previewFailed, setPreviewFailed] = useState(false);

  // ---- Persistent <img> ref (never unmounted by React) ----
  const imgRef = useRef<HTMLImageElement>(null);
  const retryCountRef = useRef(0);
  const retryTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // ---- Connect / disconnect stream preview ----
  const connectPreview = useCallback(() => {
    const img = imgRef.current;
    if (!img) return;

    retryCountRef.current = 0;
    setPreviewFailed(false);

    if (retryTimerRef.current) {
      clearTimeout(retryTimerRef.current);
      retryTimerRef.current = null;
    }

    // Set src imperatively — element stays in DOM
    img.src = `${API_BASE}/api/stream/video/${camera.id}`;
  }, [camera.id]);

  const disconnectPreview = useCallback(() => {
    const img = imgRef.current;
    if (img) {
      img.src = '';
    }

    if (retryTimerRef.current) {
      clearTimeout(retryTimerRef.current);
      retryTimerRef.current = null;
    }

    retryCountRef.current = 0;
    setPreviewFailed(false);
  }, []);

  // Reset on status change
  useEffect(() => {
    if (camera.status === 'live') {
      connectPreview();
    } else {
      disconnectPreview();
    }
    return () => {
      if (retryTimerRef.current) clearTimeout(retryTimerRef.current);
    };
  }, [camera.status]); // eslint-disable-line react-hooks/exhaustive-deps

  // ---- MJPEG preview error handler with exponential backoff ----
  function handlePreviewError() {
    if (previewFailed) return;

    retryCountRef.current += 1;

    if (retryCountRef.current > MAX_PREVIEW_RETRIES) {
      setPreviewFailed(true);
      return;
    }

    const delay = Math.min(1500 * Math.pow(1.5, retryCountRef.current - 1), 10_000);

    retryTimerRef.current = setTimeout(() => {
      const img = imgRef.current;
      if (img) {
        // Reconnect by re-setting src (element stays mounted)
        img.src = `${API_BASE}/api/stream/video/${camera.id}`;
      }
    }, delay);
  }

  /* ── API helpers ──────────────────────────────────────────── */

  async function handleStart() {
    setLoading(true);
    try {
      const res = await fetch(`${API_BASE}/api/cameras/${camera.id}/start`, {
        method: 'POST',
      });
      if (res.ok) onStatusChange(camera.id, 'live');
    } catch {
      onStatusChange(camera.id, 'live');
    } finally {
      setLoading(false);
    }
  }

  async function handleStop() {
    setLoading(true);
    try {
      const res = await fetch(`${API_BASE}/api/cameras/${camera.id}/stop`, {
        method: 'POST',
      });
      if (res.ok) onStatusChange(camera.id, 'offline');
    } catch {
      onStatusChange(camera.id, 'offline');
    } finally {
      setLoading(false);
    }
  }

  function handleDelete() {
    if (!window.confirm(`Hapus kamera "${camera.name}"?`)) return;
    (async () => {
      try {
        await fetch(`${API_BASE}/api/cameras/${camera.id}`, { method: 'DELETE' });
      } catch { /* no-op */ }
      onDelete(camera.id);
    })();
  }

  async function handleEdit(data: { name: string; rtsp_url: string }) {
    try {
      await fetch(`${API_BASE}/api/cameras/${camera.id}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data),
      });
    } catch { /* no-op */ }
    onUpdate(camera.id, data);
    setEditOpen(false);
  }

  /* ── Status helpers ────────────────────────────────────────── */

  const statusMap: Record<Camera['status'], { label: string; dotClass: string; icon: React.ElementType }> = {
    live: { label: 'Live', dotClass: 'cam-card__dot--live', icon: Wifi },
    processing: { label: 'Processing', dotClass: 'cam-card__dot--processing', icon: Loader2 },
    offline: { label: 'Offline', dotClass: 'cam-card__dot--offline', icon: WifiOff },
  };

  const { label, dotClass, icon: StatusIcon } = statusMap[camera.status];

  const shouldStream = camera.status === 'live' && !previewFailed;
  const isConnecting = camera.status === 'processing';

  return (
    <>
      <div className="cam-card" id={`cam-card-${camera.id}`}>
        {/* Preview area */}
        <div className="cam-card__preview">
          {/* Persistent <img> — never unmounted by React */}
          <img
            ref={imgRef}
            alt="preview"
            onError={handlePreviewError}
            style={{
              width: '100%',
              height: '100%',
              objectFit: 'cover',
              borderRadius: '6px 6px 0 0',
              display: shouldStream ? 'block' : 'none',
            }}
            draggable={false}
          />

          {/* Placeholder states */}
          {isConnecting ? (
            <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 8 }}>
              <Loader2 size={28} className="cam-card__preview-icon" style={{ animation: 'spin 1s linear infinite' }} />
              <span className="cam-card__preview-label">Connecting to stream…</span>
            </div>
          ) : previewFailed ? (
            <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 8 }}>
              <WifiOff size={28} className="cam-card__preview-icon" />
              <span className="cam-card__preview-label">Stream unavailable</span>
              <button
                style={{ fontSize: 11, opacity: 0.7, cursor: 'pointer' }}
                onClick={() => connectPreview()}
              >
                Retry
              </button>
            </div>
          ) : !shouldStream ? (
            <>
              <Video size={32} className="cam-card__preview-icon" />
              <span className="cam-card__preview-label">{camera.rtsp_url}</span>
            </>
          ) : null}

          {/* Status badge */}
          <span className={`cam-card__status ${dotClass}`}>
            <span className="cam-card__dot" />
            <StatusIcon size={12} />
            {label}
          </span>

          {/* Zone indicator */}
          {zonePoints.length >= 3 && (
            <span className="cam-card__zone-badge">
              <Crosshair size={10} />
              Zona aktif
            </span>
          )}
        </div>

        {/* Info */}
        <div className="cam-card__body">
          <h3 className="cam-card__name">{camera.name}</h3>
          <p className="cam-card__url">{camera.rtsp_url}</p>
        </div>

        {/* Actions */}
        <div className="cam-card__actions">
          {camera.status !== 'live' ? (
            <button
              id={`btn-start-${camera.id}`}
              className="cam-card__btn cam-card__btn--start"
              onClick={handleStart}
              disabled={loading}
              title="Start stream"
            >
              <Play size={14} />
              Start
            </button>
          ) : (
            <button
              id={`btn-stop-${camera.id}`}
              className="cam-card__btn cam-card__btn--stop"
              onClick={handleStop}
              disabled={loading}
              title="Stop stream"
            >
              <Square size={14} />
              Stop
            </button>
          )}

          <button
            id={`btn-zone-${camera.id}`}
            className="cam-card__btn cam-card__btn--zone"
            onClick={() => setZoneOpen(true)}
            title="Set Detection Zone"
          >
            <Crosshair size={14} />
            Zone
          </button>

          <button
            id={`btn-edit-${camera.id}`}
            className="cam-card__btn cam-card__btn--edit"
            onClick={() => setEditOpen(true)}
            title="Edit"
          >
            <Pencil size={14} />
          </button>

          <button
            id={`btn-delete-${camera.id}`}
            className="cam-card__btn cam-card__btn--delete"
            onClick={handleDelete}
            title="Hapus"
          >
            <Trash2 size={14} />
          </button>
        </div>
      </div>

      {/* Edit modal */}
      {editOpen && (
        <AddCameraModal
          mode="edit"
          initial={{ name: camera.name, rtsp_url: camera.rtsp_url }}
          onSubmit={handleEdit}
          onClose={() => setEditOpen(false)}
        />
      )}

      {/* Detection zone editor */}
      {zoneOpen && (
        <DetectionZoneEditor
          cameraId={camera.id}
          cameraName={camera.name}
          initialPoints={zonePoints}
          onSave={(pts) => {
            onSaveZone(camera.id, pts);
            setZoneOpen(false);
          }}
          onClose={() => setZoneOpen(false)}
        />
      )}
    </>
  );
}

// React.memo prevents re-render when parent camera list re-renders
// for reasons unrelated to this specific camera.
export default React.memo(CameraCard);