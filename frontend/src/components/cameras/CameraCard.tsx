/**
 * CameraCard — single camera entry displayed in the configuration grid.
 */

import { useState, useEffect, useRef } from 'react';
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
const WS_BASE = import.meta.env.VITE_WS_URL ?? 'ws://localhost:8000';

interface Props {
  camera: Camera;
  zonePoints: ZonePoint[];
  onUpdate: (id: string, patch: { name?: string; rtsp_url?: string }) => void;
  onDelete: (id: string) => void;
  onStatusChange: (id: string, status: Camera['status']) => void;
  onSaveZone: (id: string, points: ZonePoint[]) => void;
}

export default function CameraCard({
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
  const [previewFrame, setPreviewFrame] = useState<string | null>(null);
  const previewWsRef = useRef<WebSocket | null>(null);

  // Preview mini WebSocket
  // Preview mini WebSocket
useEffect(() => {
  if (camera.status !== 'live' && camera.status !== 'processing') {
    setPreviewFrame(null);
    if (previewWsRef.current) {
      previewWsRef.current.close();
      previewWsRef.current = null;
    }
    return;
  }

  const ws = new WebSocket(`${WS_BASE}/ws/stream/${camera.id}`);
  previewWsRef.current = ws;

  ws.onmessage = (e) => {
    try {
      const msg = JSON.parse(e.data);
      if (msg.type === 'frame' && msg.data) {
        setPreviewFrame(msg.data);
      }
    } catch { /* no-op */ }
  };

  // Only close if it's already active; otherwise, handle it gracefully
  ws.onerror = () => {
    if (ws.readyState === WebSocket.OPEN) {
      ws.close();
    }
  };

  return () => {
    // Explicitly check readyState to minimize browser console noise
    if (ws.readyState === WebSocket.CONNECTING || ws.readyState === WebSocket.OPEN) {
      ws.close();
    }
    previewWsRef.current = null;
  };
}, [camera.id, camera.status]);


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

  return (
    <>
      <div className="cam-card" id={`cam-card-${camera.id}`}>
        {/* Preview area */}
        <div className="cam-card__preview">
          {previewFrame ? (
            <img
              src={`data:image/jpeg;base64,${previewFrame}`}
              alt="preview"
              style={{
                width: '100%',
                height: '100%',
                objectFit: 'cover',
                borderRadius: '6px 6px 0 0',
              }}
              draggable={false}
            />
          ) : (
            <>
              <Video size={32} className="cam-card__preview-icon" />
              <span className="cam-card__preview-label">{camera.rtsp_url}</span>
            </>
          )}

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