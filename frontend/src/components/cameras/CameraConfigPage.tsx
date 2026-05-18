/**
 * CameraConfigPage — full page for managing cameras.
 *
 * Shows a responsive card grid of all registered cameras with
 * Start / Stop / Edit / Delete and Detection-Zone actions.
 * Includes an "Add Camera" button that opens the modal form.
 */

import { useState } from 'react';
import { Plus, Camera, RefreshCw } from 'lucide-react';
import { useCameraStore } from '@/store/cameraStore';
import type { Camera as CameraType } from '@/store/cameraStore';
import CameraCard from './CameraCard';
import AddCameraModal from './AddCameraModal';

const API_BASE = import.meta.env.VITE_API_URL ?? 'http://localhost:8000';

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

  /* ── Stats counters ────────────────────────────────────────── */
  const liveCount = cameras.filter((c) => c.status === 'live').length;
  const procCount = cameras.filter((c) => c.status === 'processing').length;
  const offCount = cameras.filter((c) => c.status === 'offline').length;

  /* ── Refresh from server ──────────────────────────────────── */
  async function handleRefresh() {
    setRefreshing(true);
    try {
      const res = await fetch(`${API_BASE}/api/cameras`);
      if (res.ok) {
        const data: CameraType[] = await res.json();
        setCameras(data);
      }
    } catch {
      /* no-op */
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
      if (res.ok) {
        const cam: CameraType = await res.json();
        addCamera(cam);
      } else {
        // Fallback: create locally with a random id
        addCamera({
          id: `cam-${Date.now()}`,
          ...data,
          status: 'offline',
        });
      }
    } catch {
      addCamera({
        id: `cam-${Date.now()}`,
        ...data,
        status: 'offline',
      });
    }
    setAddOpen(false);
  }

  return (
    <div className="cam-page">
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
              onUpdate={updateCamera}
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
