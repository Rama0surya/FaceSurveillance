/**
 * DetectionZoneEditor — full-screen overlay with an HTML Canvas
 * for drawing a polyline / polygon detection zone on top of a
 * camera preview placeholder.
 *
 * Points are stored as normalised 0-1 coordinates relative to
 * the canvas so they remain valid regardless of resolution.
 */

import { useRef, useState, useEffect, useCallback } from 'react';
import { X, Undo2, Trash2, Save, MousePointerClick } from 'lucide-react';
import type { ZonePoint } from '@/store/cameraStore';

interface Props {
  cameraName: string;
  initialPoints: ZonePoint[];
  onSave: (points: ZonePoint[]) => void;
  onClose: () => void;
}

export default function DetectionZoneEditor({
  cameraName,
  initialPoints,
  onSave,
  onClose,
}: Props) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const [points, setPoints] = useState<ZonePoint[]>(initialPoints);
  const [canvasSize, setCanvasSize] = useState({ w: 800, h: 450 });

  /* ── Resize canvas to container ────────────────────────────── */
  useEffect(() => {
    function resize() {
      if (!containerRef.current) return;
      const rect = containerRef.current.getBoundingClientRect();
      // maintain 16:9 aspect
      const w = rect.width;
      const h = Math.round(w * (9 / 16));
      setCanvasSize({ w, h });
    }
    resize();
    window.addEventListener('resize', resize);
    return () => window.removeEventListener('resize', resize);
  }, []);

  /* ── Draw ───────────────────────────────────────────────────── */
  const draw = useCallback(() => {
    const cvs = canvasRef.current;
    if (!cvs) return;
    const ctx = cvs.getContext('2d');
    if (!ctx) return;

    ctx.clearRect(0, 0, cvs.width, cvs.height);

    // placeholder background
    ctx.fillStyle = '#1F2937';
    ctx.fillRect(0, 0, cvs.width, cvs.height);

    // grid overlay for visual reference
    ctx.strokeStyle = 'rgba(255,255,255,0.06)';
    ctx.lineWidth = 1;
    for (let i = 1; i < 8; i++) {
      const x = (cvs.width / 8) * i;
      ctx.beginPath(); ctx.moveTo(x, 0); ctx.lineTo(x, cvs.height); ctx.stroke();
    }
    for (let i = 1; i < 5; i++) {
      const y = (cvs.height / 5) * i;
      ctx.beginPath(); ctx.moveTo(0, y); ctx.lineTo(cvs.width, y); ctx.stroke();
    }

    // camera name watermark
    ctx.fillStyle = 'rgba(255,255,255,0.12)';
    ctx.font = '14px Inter, sans-serif';
    ctx.fillText(cameraName, 16, 28);

    if (points.length === 0) return;

    // draw polyline
    ctx.beginPath();
    ctx.strokeStyle = '#22c55e';
    ctx.lineWidth = 2;
    ctx.lineJoin = 'round';
    points.forEach((p, i) => {
      const px = p.x * cvs.width;
      const py = p.y * cvs.height;
      if (i === 0) ctx.moveTo(px, py);
      else ctx.lineTo(px, py);
    });

    // close polygon if ≥ 3 points
    if (points.length >= 3) {
      ctx.closePath();
      ctx.fillStyle = 'rgba(34, 197, 94, 0.15)';
      ctx.fill();
    }
    ctx.stroke();

    // draw vertices
    points.forEach((p, i) => {
      const px = p.x * cvs.width;
      const py = p.y * cvs.height;

      ctx.beginPath();
      ctx.arc(px, py, 5, 0, Math.PI * 2);
      ctx.fillStyle = i === 0 ? '#16a34a' : '#22c55e';
      ctx.fill();
      ctx.strokeStyle = '#fff';
      ctx.lineWidth = 1.5;
      ctx.stroke();
    });
  }, [points, cameraName]);

  useEffect(() => {
    draw();
  }, [draw, canvasSize]);

  /* ── Click handler ─────────────────────────────────────────── */
  function handleCanvasClick(e: React.MouseEvent<HTMLCanvasElement>) {
    const cvs = canvasRef.current;
    if (!cvs) return;
    const rect = cvs.getBoundingClientRect();
    const x = (e.clientX - rect.left) / rect.width;
    const y = (e.clientY - rect.top) / rect.height;
    setPoints((prev) => [...prev, { x, y }]);
  }

  function undoLast() {
    setPoints((prev) => prev.slice(0, -1));
  }

  function clearAll() {
    setPoints([]);
  }

  function handleSave() {
    onSave(points);
  }

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div
        className="zone-editor"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="zone-editor__header">
          <h2 className="zone-editor__title">
            <MousePointerClick size={18} />
            Detection Zone — {cameraName}
          </h2>
          <button className="cam-modal__close" onClick={onClose} title="Tutup">
            <X size={18} />
          </button>
        </div>

        {/* Canvas */}
        <div className="zone-editor__canvas-wrap" ref={containerRef}>
          <canvas
            ref={canvasRef}
            width={canvasSize.w}
            height={canvasSize.h}
            className="zone-editor__canvas"
            onClick={handleCanvasClick}
          />
        </div>

        {/* Hint */}
        <p className="zone-editor__hint">
          Klik pada canvas untuk menambahkan titik. Minimal 3 titik untuk membuat zona polygon.
          Titik disimpan sebagai koordinat relatif (0–1).
        </p>

        {/* Toolbar */}
        <div className="zone-editor__toolbar">
          <div className="zone-editor__toolbar-left">
            <button
              className="zone-editor__btn zone-editor__btn--secondary"
              onClick={undoLast}
              disabled={points.length === 0}
            >
              <Undo2 size={14} />
              Undo
            </button>
            <button
              className="zone-editor__btn zone-editor__btn--danger"
              onClick={clearAll}
              disabled={points.length === 0}
            >
              <Trash2 size={14} />
              Hapus Semua
            </button>
            <span className="zone-editor__count">
              {points.length} titik
            </span>
          </div>
          <button
            className="zone-editor__btn zone-editor__btn--primary"
            onClick={handleSave}
          >
            <Save size={14} />
            Simpan Zona
          </button>
        </div>
      </div>
    </div>
  );
}
