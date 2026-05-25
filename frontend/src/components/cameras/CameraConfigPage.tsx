/**
 * CameraConfigPage — full page for managing cameras.
 *
 * Fixes applied:
 *  1. Removed the catch fallback that created fake local cam-{timestamp} IDs.
 *     These phantom cameras only existed in React memory, causing:
 *     - NS_ERROR_NET_TIMEOUT on cam-1779593842032 style stream requests
 *     - Cameras disappearing on page refresh (never in DB)
 *  2. Added proper error toast when adding camera fails
 *  3. Added RTSP reachability warning after successful add
 *  4. Cameras now only added to store after confirmed DB save
 */

import { useState } from 'react';
import { Plus, Camera, RefreshCw, AlertTriangle, X } from 'lucide-react';
import { useCameraStore } from '@/store/cameraStore';
import type { Camera as CameraType } from '@/store/cameraStore';
import CameraCard from './CameraCard';
import AddCameraModal from './AddCameraModal';

const API_BASE = import.meta.env.VITE_API_URL ?? 'http://localhost:8000';

// ------------------------------------------------------------------
// Inline toast — lightweight, no extra dependency
// ------------------------------------------------------------------
interface Toast {
  id: number;
  type: 'error' | 'warning' | 'success';
  message: string;
}

let _toastId = 0;

export default function CameraConfigPage() {
  const cameras = useCameraStore((s) => s.cameras);
  const detectionZones = useCameraStore((s) => s.detectionZones);
  const addCamera = useCameraStore((s) => s.addCamera);
  const updateCamera = useCameraStore((s) => s.updateCamera);
  const removeCamera = useCameraStore((s) => s.removeCamera);
  const updateCameraStatus = useCameraStore((s) => s.updateCameraStatus);
  const setCameras = useCameraStore((s) => s.setCameras);
  const setDetectionZone = useCameraStore((s) => s.setDetectionZone);

  const [addOpen, setAddOpen] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [toasts, setToasts] = useState<Toast[]>([]);

  const pushToast = (type: Toast['type'], message: string, ttl = 6000) => {
    const id = ++_toastId;
    setToasts((prev) => [...prev, { id, type, message }]);
    setTimeout(() => setToasts((prev) => prev.filter((t) => t.id !== id)), ttl);
  };

  const dismissToast = (id: number) =>
    setToasts((prev) => prev.filter((t) => t.id !== id));

  /* ── Stats counters ────────────────────────────────────────── */
  const liveCount = cameras.filter((c) => c.status === 'live').length;
  const procCount = cameras.filter((c) => c.status === 'processing').length;
  const offCount  = cameras.filter((c) => c.status === 'offline').length;

  /* ── Refresh from server ──────────────────────────────────── */
  async function handleRefresh() {
    setRefreshing(true);
    try {
      const res = await fetch(`${API_BASE}/api/cameras`);
      if (res.ok) {
        const data: CameraType[] = await res.json();
        setCameras(data);
      } else {
        pushToast('error', `Gagal refresh kamera: ${res.status} ${res.statusText}`);
      }
    } catch (err) {
      pushToast('error', 'Tidak dapat terhubung ke backend. Periksa koneksi jaringan.');
    } finally {
      setRefreshing(false);
    }
  }

  /* ── Add camera ──────────────────────────────────────────── */
  async function handleAddCamera(data: { name: string; rtsp_url: string }) {
    try {
      const res = await fetch(`${API_BASE}/api/cameras`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data),
      });

      if (!res.ok) {
        // Show specific error — do NOT create a fake local camera
        let detail = `${res.status} ${res.statusText}`;
        try {
          const body = await res.json();
          detail = body?.detail ?? detail;
        } catch { /* ignore parse error */ }

        pushToast(
          'error',
          `Gagal menambah kamera: ${detail}. ` +
          'Pastikan backend berjalan dan tidak ada masalah CORS.',
        );
        return; // ← Critical: stop here, don't add phantom camera
      }

      const cam: CameraType = await res.json();

      // Only add to store after confirmed DB save with real UUID
      addCamera(cam);
      setAddOpen(false);

      // Warn if RTSP URL unreachable (non-blocking probe)
      fetch(`${API_BASE}/api/cameras/${cam.id}/probe`, { method: 'POST' })
        .then((r) => r.json())
        .then((probe) => {
          if (!probe.reachable) {
            pushToast(
              'warning',
              `Kamera "${cam.name}" berhasil disimpan, tapi RTSP tidak dapat dijangkau: ${probe.message}`,
              10_000,
            );
          } else {
            pushToast('success', `Kamera "${cam.name}" berhasil ditambahkan.`);
          }
        })
        .catch(() => {
          pushToast('success', `Kamera "${cam.name}" berhasil ditambahkan.`);
        });

    } catch (err) {
      // Network-level failure (no response at all — likely CORS or backend down)
      pushToast(
        'error',
        'Tidak dapat menghubungi backend. ' +
        'Kemungkinan masalah CORS atau backend tidak aktif. ' +
        'Periksa console browser untuk detail.',
      );
      // Do NOT create a fake local camera here
    }
  }

  /* ── Update camera ───────────────────────────────────────── */
  async function handleUpdateCamera(
    id: string,
    patch: { name?: string; rtsp_url?: string },
  ) {
    try {
      const res = await fetch(`${API_BASE}/api/cameras/${id}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(patch),
      });
      if (res.ok) {
        updateCamera(id, patch);
      } else {
        pushToast('error', `Gagal update kamera: ${res.status}`);
      }
    } catch {
      pushToast('error', 'Gagal update kamera. Periksa koneksi jaringan.');
    }
  }

  return (
    <div className="cam-page">
      {/* Toast container */}
      <div className="fixed bottom-4 right-4 z-50 flex flex-col gap-2">
        {toasts.map((t) => (
          <div
            key={t.id}
            className={`flex items-start gap-2 rounded-lg px-4 py-3 text-sm shadow-lg max-w-sm ${
              t.type === 'error'
                ? 'border border-red-500/40 bg-red-900/80 text-red-200'
                : t.type === 'warning'
                ? 'border border-amber-500/40 bg-amber-900/80 text-amber-200'
                : 'border border-green-500/40 bg-green-900/80 text-green-200'
            }`}
          >
            <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
            <span className="flex-1 leading-relaxed">{t.message}</span>
            <button onClick={() => dismissToast(t.id)} className="ml-2 shrink-0 opacity-60 hover:opacity-100">
              <X className="h-3.5 w-3.5" />
            </button>
          </div>
        ))}
      </div>

      {/* Page header */}
      <div className="cam-page__header">
        <div className="cam-page__header-left">
          <Camera size={22} className="cam-page__header-icon" />
          <div>
            <h1 className="cam-page__title">Konfigurasi Kamera</h1>
            <p className="cam-page__subtitle">
              Kelola kamera CCTV, atur stream, dan tentukan zona deteksi.
            </p>
          </div>
        </div>

        <div className="cam-page__header-right">
          <button
            id="btn-refresh-cameras"
            className="cam-page__btn cam-page__btn--secondary"
            onClick={handleRefresh}
            disabled={refreshing}
          >
            <RefreshCw size={14} className={refreshing ? 'spin' : ''} />
            Refresh
          </button>

          <button
            id="btn-add-camera"
            className="cam-page__btn cam-page__btn--primary"
            onClick={() => setAddOpen(true)}
          >
            <Plus size={16} />
            Tambah Kamera
          </button>
        </div>
      </div>

      {/* Status summary */}
      <div className="cam-page__summary">
        <div className="cam-page__stat">
          <span className="cam-page__stat-dot cam-page__stat-dot--total" />
          <span className="cam-page__stat-label">Total</span>
          <span className="cam-page__stat-value">{cameras.length}</span>
        </div>
        <div className="cam-page__stat">
          <span className="cam-page__stat-dot cam-page__stat-dot--live" />
          <span className="cam-page__stat-label">Live</span>
          <span className="cam-page__stat-value">{liveCount}</span>
        </div>
        <div className="cam-page__stat">
          <span className="cam-page__stat-dot cam-page__stat-dot--processing" />
          <span className="cam-page__stat-label">Processing</span>
          <span className="cam-page__stat-value">{procCount}</span>
        </div>
        <div className="cam-page__stat">
          <span className="cam-page__stat-dot cam-page__stat-dot--offline" />
          <span className="cam-page__stat-label">Offline</span>
          <span className="cam-page__stat-value">{offCount}</span>
        </div>
      </div>

      {/* Camera grid */}
      {cameras.length === 0 ? (
        <div className="cam-page__empty">
          <Camera size={48} className="cam-page__empty-icon" />
          <p>Belum ada kamera terdaftar.</p>
          <button
            className="cam-page__btn cam-page__btn--primary"
            onClick={() => setAddOpen(true)}
          >
            <Plus size={16} />
            Tambah Kamera Pertama
          </button>
        </div>
      ) : (
        <div className="cam-page__grid">
          {cameras.map((cam) => (
            <CameraCard
              key={cam.id}
              camera={cam}
              zonePoints={detectionZones[cam.id] ?? []}
              onUpdate={handleUpdateCamera}
              onDelete={removeCamera}
              onStatusChange={updateCameraStatus}
              onSaveZone={setDetectionZone}
            />
          ))}
        </div>
      )}

      {/* Add modal */}
      {addOpen && (
        <AddCameraModal
          mode="add"
          onSubmit={handleAddCamera}
          onClose={() => setAddOpen(false)}
        />
      )}
    </div>
  );
}
