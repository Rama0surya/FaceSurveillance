/**
 * LiveVideoPanel — persistent MJPEG stream with canvas bounding-box overlay.
 *
 * Architecture (Layer 2 — Web Page):
 *   The `<img>` element is NEVER unmounted by React.  Its `src` attribute
 *   is changed imperatively via a ref, so the browser merely opens a new
 *   HTTP connection to the MJPEG endpoint — the element stays in the DOM
 *   across re-renders, page navigations, and snapshot events.
 *
 *   Bounding boxes are drawn on a `<canvas>` overlay positioned on top of
 *   the `<img>`.  Canvas updates are purely imperative (requestAnimationFrame),
 *   so they NEVER trigger React reconciliation or DOM mutations that could
 *   interfere with the video stream.
 *
 * Key invariants:
 *   - <img> is never key-ed → React never unmounts it
 *   - Snapshot / detection events update the store → canvas redraws
 *   - Page refresh only kills the HTTP connection; RTSP reader stays alive
 *   - Reconnect is instant: just re-set img.src
 */

import React, { useEffect, useRef, useCallback, memo } from 'react';
import { useCameraStore } from '@/store/cameraStore';
import { Video, WifiOff, RefreshCw } from 'lucide-react';

/* Emotion → bbox / label color */
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

const API_BASE = import.meta.env.VITE_API_URL ?? 'http://localhost:8000';

// Hard cap on stream reconnect attempts before giving up
const MAX_STREAM_RETRIES = 10;

function LiveVideoPanel() {
  const currentFaces = useCameraStore((s) => s.currentFaces);
  const activeCamera = useCameraStore((s) => s.activeCamera);
  const isLive = useCameraStore((s) => s.isLive);
  const pipelineToggles = useCameraStore((s) => s.pipelineToggles);

  // ---- Refs for persistent elements (never unmounted by React) ----
  const imgRef = useRef<HTMLImageElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const retryCountRef = useRef(0);
  const retryTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const streamFailedRef = useRef(false);

  // ---- State for UI-only rendering (error message, timestamp) ----
  // We keep a simple state flag for the "stream failed" placeholder
  const [streamFailed, setStreamFailed] = React.useState(false);
  const [timestamp, setTimestamp] = React.useState(() =>
    new Date().toLocaleString('en-GB', {
      day: '2-digit', month: '2-digit', year: 'numeric',
      hour: '2-digit', minute: '2-digit', second: '2-digit',
    })
  );

  // ---- Tick clock every second ----
  useEffect(() => {
    const id = setInterval(() => {
      setTimestamp(
        new Date().toLocaleString('en-GB', {
          day: '2-digit', month: '2-digit', year: 'numeric',
          hour: '2-digit', minute: '2-digit', second: '2-digit',
        })
      );
    }, 1000);
    return () => clearInterval(id);
  }, []);

  // ================================================================
  // Stream connection — imperative src assignment (no React key)
  // ================================================================

  const connectStream = useCallback((cameraId: string) => {
    const img = imgRef.current;
    if (!img) return;

    // Reset retry state
    retryCountRef.current = 0;
    streamFailedRef.current = false;
    setStreamFailed(false);

    // Clear any pending retry timer
    if (retryTimerRef.current) {
      clearTimeout(retryTimerRef.current);
      retryTimerRef.current = null;
    }

    // Set src imperatively — the <img> element stays in the DOM,
    // only the HTTP connection changes.  This is the KEY difference
    // from the old key-based approach.
    img.src = `${API_BASE}/api/stream/video/${cameraId}`;
  }, []);

  const disconnectStream = useCallback(() => {
    const img = imgRef.current;
    if (img) {
      // Setting src to empty string aborts the current MJPEG connection
      // without removing the DOM element.
      img.src = '';
    }

    if (retryTimerRef.current) {
      clearTimeout(retryTimerRef.current);
      retryTimerRef.current = null;
    }

    retryCountRef.current = 0;
    streamFailedRef.current = false;
    setStreamFailed(false);
  }, []);

  // ---- Handle stream error (with exponential backoff retry) ----
  const handleStreamError = useCallback(() => {
    if (streamFailedRef.current) return;
    if (!activeCamera?.id) return;

    retryCountRef.current += 1;

    if (retryCountRef.current > MAX_STREAM_RETRIES) {
      streamFailedRef.current = true;
      setStreamFailed(true);
      return;
    }

    // Exponential backoff: 1s, 2s, 4s … capped at 10s
    const delay = Math.min(1000 * Math.pow(2, retryCountRef.current - 1), 10_000);
    const camId = activeCamera.id;

    retryTimerRef.current = setTimeout(() => {
      const img = imgRef.current;
      if (img) {
        // Re-set src to trigger reconnect (element stays mounted)
        img.src = `${API_BASE}/api/stream/video/${camId}`;
      }
    }, delay);
  }, [activeCamera?.id]);

  // ---- Manual retry button ----
  const handleManualRetry = useCallback(() => {
    if (activeCamera?.id) {
      connectStream(activeCamera.id);
    }
  }, [activeCamera?.id, connectStream]);

  // ---- Connect/disconnect on camera change ----
  useEffect(() => {
    if (activeCamera?.id && isLive) {
      connectStream(activeCamera.id);
    } else {
      disconnectStream();
    }
    return () => {
      disconnectStream();
    };
  }, [activeCamera?.id, isLive]); // eslint-disable-line react-hooks/exhaustive-deps

  // ================================================================
  // Canvas bounding-box overlay — purely imperative, no React DOM
  // ================================================================

  useEffect(() => {
    const canvas = canvasRef.current;
    const img = imgRef.current;
    if (!canvas || !img) return;

    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    // Match canvas size to the rendered image size
    const rect = img.getBoundingClientRect();
    const dpr = window.devicePixelRatio || 1;
    canvas.width = rect.width * dpr;
    canvas.height = rect.height * dpr;
    canvas.style.width = `${rect.width}px`;
    canvas.style.height = `${rect.height}px`;
    ctx.scale(dpr, dpr);

    // Clear previous frame's boxes
    ctx.clearRect(0, 0, rect.width, rect.height);

    if (!currentFaces.length) return;

    // We need to know the "natural" resolution of the stream to scale
    // bounding box coordinates.  The MJPEG stream sends whatever resolution
    // the camera provides (commonly 640×480 or 1920×1080).
    // We use the img's natural dimensions as the coordinate space.
    const natW = img.naturalWidth || 640;
    const natH = img.naturalHeight || 480;
    const scaleX = rect.width / natW;
    const scaleY = rect.height / natH;

    for (const face of currentFaces) {
      const x = face.bbox.x * scaleX;
      const y = face.bbox.y * scaleY;
      const w = face.bbox.w * scaleX;
      const h = face.bbox.h * scaleY;
      const color = BBOX_COLORS[face.emotion] ?? '#3b82f6';

      // Draw bounding box
      ctx.strokeStyle = color;
      ctx.lineWidth = 2;
      ctx.strokeRect(x, y, w, h);

      // Draw label background
      const label = `${face.gender === 'male' ? '♂' : '♀'} ${EMOTION_SHORT[face.emotion] ?? face.emotion}`;
      ctx.font = '600 11px Inter, sans-serif';
      const metrics = ctx.measureText(label);
      const labelH = 18;
      const labelW = metrics.width + 8;

      ctx.fillStyle = color;
      ctx.globalAlpha = 0.85;
      ctx.fillRect(x, y - labelH, labelW, labelH);
      ctx.globalAlpha = 1.0;

      // Draw label text
      ctx.fillStyle = '#fff';
      ctx.fillText(label, x + 4, y - 5);
    }
  }, [currentFaces]);

  // ================================================================
  // Render
  // ================================================================

  const shouldStream = isLive && activeCamera && !streamFailed;

  return (
    <div className="live-panel" id="live-video-panel">
      <div className="live-panel__viewport">

        {/* ---- Persistent stream <img> — NEVER unmounted ---- */}
        <img
          ref={imgRef}
          alt="Live feed"
          className="live-panel__frame"
          draggable={false}
          onError={handleStreamError}
          style={{
            display: shouldStream ? 'block' : 'none',
          }}
        />

        {/* ---- Canvas overlay for bounding boxes ---- */}
        {shouldStream && (
          <canvas
            ref={canvasRef}
            className="live-panel__overlay"
            style={{
              position: 'absolute',
              top: 0,
              left: 0,
              width: '100%',
              height: '100%',
              pointerEvents: 'none',
            }}
          />
        )}

        {/* ---- Placeholder states ---- */}
        {streamFailed ? (
          <div className="live-panel__placeholder">
            <WifiOff size={48} className="live-panel__placeholder-icon" />
            <span>Stream unavailable after {MAX_STREAM_RETRIES} retries</span>
            <button
              onClick={handleManualRetry}
              style={{ marginTop: 12, display: 'flex', alignItems: 'center', gap: 6, cursor: 'pointer' }}
            >
              <RefreshCw size={14} />
              Retry
            </button>
          </div>
        ) : !shouldStream ? (
          <div className="live-panel__placeholder">
            <Video size={48} className="live-panel__placeholder-icon" />
            <span>
              {activeCamera
                ? 'Connecting…'
                : 'Select a camera to begin'}
            </span>
          </div>
        ) : null}

        {/* Pipeline status indicators — top-right */}
        <div className="stream-indicators">
          <span className={`stream-indicator ${pipelineToggles.tracking_enabled ? 'stream-indicator--on' : 'stream-indicator--off'}`}>
            <span className="stream-indicator__dot" />
            T
          </span>
          <span className={`stream-indicator ${pipelineToggles.insightface_enabled ? 'stream-indicator--on' : 'stream-indicator--off'}`}>
            <span className="stream-indicator__dot" />
            A
          </span>
        </div>

        {/* Warning bar when face analysis is OFF */}
        {!pipelineToggles.insightface_enabled && isLive && activeCamera && (
          <div className="stream-warning-bar">
            ⚠️ Face analysis is disabled — no age/gender/emotion detection
          </div>
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

// React.memo prevents re-render when parent (DashboardPage) re-renders
// due to snapshot/stats updates in sibling components.
export default memo(LiveVideoPanel);

