/**
 * AddCameraModal — modal form to create or edit a camera entry.
 *
 * Props:
 *   mode        'add' | 'edit'
 *   initial     Pre-filled values when editing
 *   onSubmit    Called with { name, rtsp_url }
 *   onClose     Close the modal
 */

import { useState, useEffect } from 'react';
import { X, Camera, Plus, Save } from 'lucide-react';

export interface CameraFormData {
  name: string;
  rtsp_url: string;
}

interface Props {
  mode: 'add' | 'edit';
  initial?: CameraFormData;
  onSubmit: (data: CameraFormData) => void;
  onClose: () => void;
}

export default function AddCameraModal({ mode, initial, onSubmit, onClose }: Props) {
  const [name, setName] = useState(initial?.name ?? '');
  const [rtspUrl, setRtspUrl] = useState(initial?.rtsp_url ?? '');
  const [error, setError] = useState('');

  useEffect(() => {
    if (initial) {
      setName(initial.name);
      setRtspUrl(initial.rtsp_url);
    }
  }, [initial]);

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!name.trim()) {
      setError('Nama kamera wajib diisi');
      return;
    }
    if (!rtspUrl.trim()) {
      setError('URL stream wajib diisi');
      return;
    }
    setError('');
    onSubmit({ name: name.trim(), rtsp_url: rtspUrl.trim() });
  }

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div
        className="cam-modal"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="cam-modal__header">
          <div className="cam-modal__header-left">
            <Camera size={18} />
            <h2 className="cam-modal__title">
              {mode === 'add' ? 'Tambah Kamera Baru' : 'Edit Kamera'}
            </h2>
          </div>
          <button
            className="cam-modal__close"
            onClick={onClose}
            title="Tutup"
          >
            <X size={18} />
          </button>
        </div>

        {/* Form */}
        <form className="cam-modal__form" onSubmit={handleSubmit}>
          {error && (
            <div className="cam-modal__error">{error}</div>
          )}

          <label className="cam-modal__label">
            Nama Kamera
            <input
              id="input-camera-name"
              className="cam-modal__input"
              type="text"
              placeholder="Contoh: Lobby Utama"
              value={name}
              onChange={(e) => setName(e.target.value)}
              autoFocus
            />
          </label>

          <label className="cam-modal__label">
            RTSP / HLS URL
            <input
              id="input-camera-url"
              className="cam-modal__input"
              type="text"
              placeholder="rtsp://192.168.1.10:554/stream1"
              value={rtspUrl}
              onChange={(e) => setRtspUrl(e.target.value)}
            />
          </label>

          <button id="btn-submit-camera" type="submit" className="cam-modal__submit">
            {mode === 'add' ? (
              <>
                <Plus size={16} />
                Tambah Kamera
              </>
            ) : (
              <>
                <Save size={16} />
                Simpan Perubahan
              </>
            )}
          </button>
        </form>
      </div>
    </div>
  );
}
