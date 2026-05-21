/**
 * DetectionZoneEditor — full-screen overlay with an HTML Canvas
 * for drawing a polyline / polygon detection zone on top of a
 * camera preview placeholder.
 *
 * Points are stored as normalised 0-1 coordinates relative to
 * the canvas so they remain valid regardless of resolution.
 */

import { useRef, useState, useEffect, useCallback } from 'react';
import { X, Undo2, Trash2, Save, MousePointerClick, ImageOff } from 'lucide-react';
import type { ZonePoint } from '@/store/cameraStore';

const API_BASE = import.meta.env.VITE_API_URL ?? 'http://localhost:8000';

interface Props {
  cameraId: string;
  cameraName: string;
  initialPoints: ZonePoint[];
  onSave: (points: ZonePoint[]) => void;
  onClose: () => void;
}

export default function DetectionZoneEditor({
  cameraId,
  cameraName,
  initialPoints,
  onSave,
  onClose,
}: Props) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const [points, setPoints] = useState<ZonePoint[]>(initialPoints);
  const [canvasSize, setCanvasSize] = useState({ w: 800, h: 450 });
  const [bgImage, setBgImage] = useState<HTMLImageElement | null>(null);
  const [bgStatus, setBgStatus] = useState<'loading' | 'loaded' | 'empty' | 'error'>('loading');

  /* —— Load snapshot terbaru sebagai background ——————————————————— */
  useEffect(() => {
    async function loadBackground() {
      try {
        const res = await fetch(
          `${API_BASE}/api/snapshots?camera_id=${cameraId}&limit=1`
        );
        if (!res.ok) { setBgStatus('error'); return; }

        const json = await res.json();
        const latestUrl: string = json.data?.[0]?.url ?? '';

        if (!latestUrl) { setBgStatus('empty'); return; }

        const fullUrl = latestUrl.startsWith('http')
          ? latestUrl
          : `${API_BASE}/${latestUrl.replace(/^\//, '')}`;

        const img = new Image();
        img.crossOrigin = 'anonymous';
        img.onload = () => { setBgImage(img); setBgStatus('loaded'); };
        img.onerror = () => setBgStatus('error');
        img.src = fullUrl;
      } catch {
        setBgStatus('error');
      }
    }
    loadBackground();
  }, [cameraId]);

  /* —— Resize canvas to container ———————————————————————————————— */
  useEffect(() => {
    function resize() {
      if (!containerRef.current) return;
      const rect = containerRef.current.getBoundingClientRect();
      const w = rect.width;
      const h = Math.round(w * (9 / 16));
      setCanvasSize({ w, h });
    }
    resize();
    window.addEventListener('resize', resize);
    return () => window.removeEventListener('resize', resize);
  }, []);

  /* —— Draw ——————————————————————————————————————————————————————— */
  const draw = useCallback(() => {
    const cvs = canvasRef.current;
    if (!cvs) return;
    const ctx = cvs.getContext('2d');
    if (!ctx) return;

    ctx.clearRect(0, 0, cvs.width, cvs.height);

    // Background: gambar snapshot atau placeholder gelap
    if (bgImage) {
      ctx.drawImage(bgImage, 0, 0, cvs.width, cvs.height);
      // overlay gelap tipis supaya polygon tetap kontras
      ctx.fillStyle = 'rgba(0, 0, 0, 0.30)';
      ctx.fillRect(0, 0, cvs.width, cvs.height);
    } else {
      ctx.fillStyle = '#1F2937';
      ctx.fillRect(0, 0, cvs.width, cvs.height);

      // grid overlay (hanya saat tidak ada background)
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
    }

    // camera name watermark
    ctx.fillStyle = 'rgba(255,255,255,0.50)';
    ctx.font = '13px Inter, sans-serif';
    ctx.fillText(cameraName, 12, 24);

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

    // close polygon if >= 3 points
    if (points.length >= 3) {
      ctx.closePath();
      ctx.fillStyle = 'rgba(34, 197, 94, 0.18)';
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
  }, [points, cameraName, bgImage]);

  useEffect(() => {
    draw();
  }, [draw, canvasSize]);

  /* —— Click handler ————————————————————————————————————————————— */
  function handleCanvasClick(e: React.MouseEvent<HTMLCanvasElement>) {
    const cvs = canvasRef.current;
    if (!cvs) return;
    const rect = cvs.getBoundingClientRect();
    const x = (e.clientX - rect.left) / rect.width;
    const y = (e.clientY - rect.top) / rect.height;
    setPoints((prev) => [...prev, { x, y }]);
  }

  function undoLast() { setPoints((prev) => prev.slice(0, -1)); }
  function clearAll() { setPoints([]); }
  function handleSave() { onSave(points); }

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="zone-editor" onClick={(e) => e.stopPropagation()}>

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

        {/* Canvas wrapper dengan status overlay */}
        <div className="zone-editor__canvas-wrap" ref={containerRef} style={{ position: 'relative' }}>
          {/* Loading indicator */}
          {bgStatus === 'loading' && (
            <div style={{
              position: 'absolute', inset: 0, display: 'flex',
              alignItems: 'center', justifyContent: 'center',
              color: 'rgba(255,255,255,0.4)', fontSize: 13, gap: 8,
              pointerEvents: 'none', zIndex: 1,
            }}>
              <span style={{
                width: 16, height: 16,
                border: '2px solid rgba(255,255,255,0.2)',
                borderTopColor: '#22c55e', borderRadius: '50%',
                display: 'inline-block',
                animation: 'zone-spin 0.8s linear infinite',
              }} />
              Memuat preview kamera...
            </div>
          )}

          {/* Empty / error state */}
          {(bgStatus === 'empty' || bgStatus === 'error') && (
            <div style={{
              position: 'absolute', inset: 0, display: 'flex',
              flexDirection: 'column', alignItems: 'center',
              justifyContent: 'center', color: 'rgba(255,255,255,0.25)',
              fontSize: 12, gap: 6, pointerEvents: 'none', zIndex: 1,
            }}>
              <ImageOff size={20} />
              {bgStatus === 'empty'
                ? 'Belum ada snapshot — mulai stream kamera terlebih dahulu'
                : 'Gagal memuat preview kamera'}
            </div>
          )}

          <canvas
            ref={canvasRef}
            width={canvasSize.w}
            height={canvasSize.h}
            className="zone-editor__canvas"
            onClick={handleCanvasClick}
            style={{ display: 'block', width: '100%', cursor: 'crosshair' }}
          />

          {/* CSS keyframe untuk spinner */}
          <style>{`
            @keyframes zone-spin {
              to { transform: rotate(360deg); }
            }
          `}</style>
        </div>

        {/* Hint */}
        <p className="zone-editor__hint">
          Klik pada canvas untuk menambahkan titik. Minimal 3 titik untuk membuat zona polygon.
          Titik disimpan sebagai koordinat relatif (0–1).
          {bgStatus === 'loaded' && (
            <span style={{ color: '#22c55e', marginLeft: 6 }}>
              ✓ Preview dari snapshot terakhir
            </span>
          )}
        </p>

        {/* Toolbar */}
        <div className="zone-editor__toolbar">
          <div className="zone-editor__toolbar-left">
            <button
              className="zone-editor__btn zone-editor__btn--secondary"
              onClick={undoLast}
              disabled={points.length === 0}
            >
              <Undo2 size={14} /> Undo
            </button>
            <button
              className="zone-editor__btn zone-editor__btn--danger"
              onClick={clearAll}
              disabled={points.length === 0}
            >
              <Trash2 size={14} /> Hapus Semua
            </button>
            <span className="zone-editor__count">{points.length} titik</span>
          </div>
          <button
            className="zone-editor__btn zone-editor__btn--primary"
            onClick={handleSave}
          >
            <Save size={14} /> Simpan Zona
          </button>
        </div>
      </div>
    </div>
  );
}
