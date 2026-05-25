/**
 * CameraCard — card component for camera list with persistent stream preview.
 *
 * Fixes applied:
 *  1. MJPEG stream URL now uses the real camera UUID (not hardcoded cam-001)
 *  2. Start stream calls /probe first — shows warning toast if RTSP unreachable
 *  3. Camera stays "offline" if RTSP is unreachable instead of showing "live"
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
  AlertTriangle,
  X,
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

// ------------------------------------------------------------------
// RTSP Warning Banner
// ------------------------------------------------------------------
interface RtspWarningProps {
  message: string;
  onDismiss: () => void;
}

function RtspWarningBanner({ message, onDismiss }: RtspWarningProps) {
  return (
    <div className="flex items-start gap-2 rounded-md border border-amber-500/40 bg-amber-500/10 px-3 py-2 text-xs text-amber-300">
      <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0 text-amber-400" />
      <span className="flex-1 leading-relaxed">{message}</span>
      <button
        onClick={onDismiss}
        className="ml-1 shrink-0 text-amber-400 hover:text-amber-200"
        aria-label="Dismiss warning"
      >
        <X className="h-3 w-3" />
      </button>
    </div>
  );
}

// ------------------------------------------------------------------
// CameraCard
// ------------------------------------------------------------------
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

  // RTSP warning state
  const [rtspWarning, setRtspWarning] = useState<string | null>(null);

  // Preview image ref — never unmounted, src changed imperatively
  const imgRef = useRef<HTMLImageElement>(null);
  const retryCountRef = useRef(0);
  const retryTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // ------------------------------------------------------------------
  // MJPEG stream URL — uses real camera UUID, NOT cam-001 style IDs
  // BUG FIX: was using hardcoded cam-001/cam-002 which don't exist as
  // backend routes. The backend registers streams by UUID.
  // ------------------------------------------------------------------
  const mjpegUrl = `${API_BASE}/api/stream/mjpeg/${camera.id}`;

  const connectPreview = useCallback(() => {
    if (!imgRef.current) return;
    retryCountRef.current = 0;
    imgRef.current.src = mjpegUrl;
  }, [mjpegUrl]);

  const disconnectPreview = useCallback(() => {
    if (retryTimerRef.current) {
      clearTimeout(retryTimerRef.current);
      retryTimerRef.current = null;
    }
    if (imgRef.current) {
      imgRef.current.src = '';
    }
    retryCountRef.current = 0;
  }, []);

  // Connect/disconnect preview based on camera status
  useEffect(() => {
    if (camera.status === 'live') {
      connectPreview();
    } else {
      disconnectPreview();
    }
    return () => disconnectPreview();
  }, [camera.status, connectPreview, disconnectPreview]);

  // Handle MJPEG stream errors with exponential backoff retry
  const handleImgError = useCallback(() => {
    if (retryCountRef.current >= MAX_PREVIEW_RETRIES) return;
    retryCountRef.current += 1;
    const delay = Math.min(1000 * 2 ** retryCountRef.current, 30_000);
    retryTimerRef.current = setTimeout(() => {
      if (imgRef.current && camera.status === 'live') {
        imgRef.current.src = `${mjpegUrl}?t=${Date.now()}`;
      }
    }, delay);
  }, [camera.status, mjpegUrl]);

  // ------------------------------------------------------------------
  // Start stream — probe RTSP first, show warning if unreachable
  // ------------------------------------------------------------------
  const handleStart = async () => {
    setLoading(true);
    setRtspWarning(null);

    try {
      // Step 1: Probe RTSP reachability (fast, 3s timeout)
      const probeRes = await fetch(`${API_BASE}/api/cameras/${camera.id}/probe`, {
        method: 'POST',
      });
      const probeData = await probeRes.json();

      if (!probeData.reachable) {
        // Camera is unreachable — show warning, do NOT start stream
        setRtspWarning(probeData.message);
        onStatusChange(camera.id, 'offline');
        setLoading(false);
        return;
      }

      // Step 2: RTSP is reachable — start the stream
      const startRes = await fetch(`${API_BASE}/api/cameras/${camera.id}/start`, {
        method: 'POST',
      });

      if (!startRes.ok) {
        const errData = await startRes.json().catch(() => ({}));
        const msg = errData?.detail?.message || errData?.detail || 'Failed to start stream';
        setRtspWarning(msg);
        onStatusChange(camera.id, 'offline');
        return;
      }

      onStatusChange(camera.id, 'processing');
      // Status will transition to 'live' once the stream is confirmed open
      // (via WebSocket status update or polling)
    } catch (err) {
      setRtspWarning(
        'Cannot connect to the backend. Check your network connection.',
      );
    } finally {
      setLoading(false);
    }
  };

  const handleStop = async () => {
    setLoading(true);
    setRtspWarning(null);
    try {
      await fetch(`${API_BASE}/api/cameras/${camera.id}/stop`, { method: 'POST' });
      onStatusChange(camera.id, 'offline');
      disconnectPreview();
    } catch (err) {
      console.error('Stop stream failed:', err);
    } finally {
      setLoading(false);
    }
  };

  const handleDelete = async () => {
    if (!confirm(`Delete camera "${camera.name}"?`)) return;
    try {
      await fetch(`${API_BASE}/api/cameras/${camera.id}`, { method: 'DELETE' });
      onDelete(camera.id);
    } catch (err) {
      console.error('Delete camera failed:', err);
    }
  };

  // ------------------------------------------------------------------
  // Status badge
  // ------------------------------------------------------------------
  const statusBadge = () => {
    switch (camera.status) {
      case 'live':
        return (
          <span className="flex items-center gap-1 rounded-full bg-green-500/20 px-2 py-0.5 text-xs font-medium text-green-400">
            <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-green-400" />
            Live
          </span>
        );
      case 'processing':
        return (
          <span className="flex items-center gap-1 rounded-full bg-blue-500/20 px-2 py-0.5 text-xs font-medium text-blue-400">
            <Loader2 className="h-3 w-3 animate-spin" />
            Connecting…
          </span>
        );
      default:
        return (
          <span className="flex items-center gap-1 rounded-full bg-gray-500/20 px-2 py-0.5 text-xs font-medium text-gray-400">
            <WifiOff className="h-3 w-3" />
            Offline
          </span>
        );
    }
  };

  const isStreaming = camera.status === 'live' || camera.status === 'processing';

  return (
    <div className="flex flex-col gap-3 rounded-xl border border-white/10 bg-white/5 p-4">
      {/* Header row */}
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-2 min-w-0">
          <Video className="h-4 w-4 shrink-0 text-blue-400" />
          <span className="truncate text-sm font-medium text-white">{camera.name}</span>
        </div>
        {statusBadge()}
      </div>

      {/* RTSP URL */}
      <p className="truncate text-xs text-gray-400" title={camera.rtsp_url}>
        {camera.rtsp_url}
      </p>

      {/* RTSP warning banner */}
      {rtspWarning && (
        <RtspWarningBanner
          message={rtspWarning}
          onDismiss={() => setRtspWarning(null)}
        />
      )}

      {/* MJPEG preview — only visible when live */}
      <div
        className={`overflow-hidden rounded-lg bg-black transition-all ${
          camera.status === 'live' ? 'h-36' : 'h-0'
        }`}
      >
        {/* eslint-disable-next-line jsx-a11y/alt-text */}
        <img
          ref={imgRef}
          onError={handleImgError}
          className="h-full w-full object-contain"
        />
      </div>

      {/* Action buttons */}
      <div className="flex items-center gap-2">
        {/* Start / Stop */}
        {!isStreaming ? (
          <button
            onClick={handleStart}
            disabled={loading}
            className="flex items-center gap-1.5 rounded-lg bg-blue-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-blue-500 disabled:opacity-50"
          >
            {loading ? (
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
            ) : (
              <Play className="h-3.5 w-3.5" />
            )}
            {loading ? 'Checking…' : 'Start'}
          </button>
        ) : (
          <button
            onClick={handleStop}
            disabled={loading}
            className="flex items-center gap-1.5 rounded-lg bg-red-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-red-500 disabled:opacity-50"
          >
            {loading ? (
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
            ) : (
              <Square className="h-3.5 w-3.5" />
            )}
            Stop
          </button>
        )}

        {/* Detection zone */}
        <button
          onClick={() => setZoneOpen(true)}
          className="flex items-center gap-1.5 rounded-lg border border-white/10 px-3 py-1.5 text-xs font-medium text-gray-300 hover:bg-white/5"
        >
          <Crosshair className="h-3.5 w-3.5" />
          Zone
        </button>

        {/* Edit */}
        <button
          onClick={() => setEditOpen(true)}
          className="flex items-center gap-1.5 rounded-lg border border-white/10 px-3 py-1.5 text-xs font-medium text-gray-300 hover:bg-white/5"
        >
          <Pencil className="h-3.5 w-3.5" />
          Edit
        </button>

        {/* Delete */}
        <button
          onClick={handleDelete}
          className="ml-auto flex items-center gap-1.5 rounded-lg border border-red-500/30 px-3 py-1.5 text-xs font-medium text-red-400 hover:bg-red-500/10"
        >
          <Trash2 className="h-3.5 w-3.5" />
          Delete
        </button>
      </div>

      {/* Modals */}
      {editOpen && (
        <AddCameraModal
          camera={camera}
          onClose={() => setEditOpen(false)}
          onSave={(patch) => {
            onUpdate(camera.id, patch);
            setEditOpen(false);
            // Clear stale warning if URL was updated
            setRtspWarning(null);
          }}
        />
      )}
      {zoneOpen && (
        <DetectionZoneEditor
          camera={camera}
          initialPoints={zonePoints}
          onClose={() => setZoneOpen(false)}
          onSave={(points) => {
            onSaveZone(camera.id, points);
            setZoneOpen(false);
          }}
        />
      )}
    </div>
  );
}

export default CameraCard;