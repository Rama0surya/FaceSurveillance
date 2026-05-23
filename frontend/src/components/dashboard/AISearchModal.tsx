import React, { useState, useRef } from 'react';
import { X, Search, Image as ImageIcon, Sliders, Upload, Play } from 'lucide-react';
import { searchSnapshotsByText, searchSnapshotsByImage, SearchSnapshotRow } from '../../lib/api';

interface AISearchModalProps {
  isOpen: boolean;
  onClose: () => void;
  cameraId?: string;
  onSearchComplete: (results: SearchSnapshotRow[], mode: 'text' | 'image', queryText?: string) => void;
}

export default function AISearchModal({ isOpen, onClose, cameraId, onSearchComplete }: AISearchModalProps) {
  const [activeTab, setActiveTab] = useState<'text' | 'image'>('text');
  const [textQuery, setTextQuery] = useState('');
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [similarity, setSimilarity] = useState(0.15);
  const [limit, setLimit] = useState(20);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fileInputRef = useRef<HTMLInputElement>(null);

  if (!isOpen) return null;

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files[0]) {
      const file = e.target.files[0];
      setSelectedFile(file);
      setPreviewUrl(URL.createObjectURL(file));
      setError(null);
    }
  };

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    if (e.dataTransfer.files && e.dataTransfer.files[0]) {
      const file = e.dataTransfer.files[0];
      setSelectedFile(file);
      setPreviewUrl(URL.createObjectURL(file));
      setError(null);
    }
  };

  const triggerFileSelect = () => {
    fileInputRef.current?.click();
  };

  const handleSearch = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError(null);

    try {
      if (activeTab === 'text') {
        if (!textQuery.trim()) {
          throw new Error('Masukkan deskripsi teks pencarian.');
        }
        const res = await searchSnapshotsByText({
          query: textQuery,
          cameraId,
          limit,
          similarityThreshold: similarity,
        });
        onSearchComplete(res.data, 'text', textQuery);
      } else {
        if (!selectedFile) {
          throw new Error('Silakan pilih atau seret gambar wajah untuk pencarian.');
        }
        const res = await searchSnapshotsByImage({
          file: selectedFile,
          cameraId,
          limit,
          similarityThreshold: similarity,
        });
        onSearchComplete(res.data, 'image', selectedFile.name);
      }
      onClose();
    } catch (err: any) {
      setError(err.message || 'Pencarian AI gagal.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="snap-modal-overlay">
      <div className="snap-modal" style={{ maxWidth: '520px', width: '100%', padding: '0', overflow: 'hidden' }}>
        
        {/* Header */}
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '16px 20px', borderBottom: '1px solid var(--border-color)' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <Search size={18} style={{ color: 'var(--accent-blue)' }} />
            <h3 style={{ margin: 0, fontSize: '16px', fontWeight: 700, color: 'var(--text-primary)' }}>Pencarian Wajah Pintar (AI Search)</h3>
          </div>
          <button onClick={onClose} style={{ background: 'none', border: 'none', color: 'var(--text-muted)', cursor: 'pointer', display: 'flex', padding: '4px' }}>
            <X size={18} />
          </button>
        </div>

        {/* Tab Selection */}
        <div style={{ display: 'flex', borderBottom: '1px solid var(--border-color)', background: 'var(--bg-primary)' }}>
          <button
            type="button"
            onClick={() => { setActiveTab('text'); setError(null); }}
            style={{
              flex: 1,
              padding: '12px',
              border: 'none',
              background: 'none',
              fontSize: '13px',
              fontWeight: 600,
              cursor: 'pointer',
              color: activeTab === 'text' ? 'var(--accent-blue)' : 'var(--text-secondary)',
              borderBottom: activeTab === 'text' ? '2px solid var(--accent-blue)' : '2px solid transparent',
              display: 'flex',
              alignItems: 'center',
              justify-content: 'center',
              gap: '6px',
              transition: 'all 0.2s ease',
            }}
          >
            <Search size={14} />
            <span>Search by Text</span>
          </button>
          <button
            type="button"
            onClick={() => { setActiveTab('image'); setError(null); }}
            style={{
              flex: 1,
              padding: '12px',
              border: 'none',
              background: 'none',
              fontSize: '13px',
              fontWeight: 600,
              cursor: 'pointer',
              color: activeTab === 'image' ? 'var(--accent-blue)' : 'var(--text-secondary)',
              borderBottom: activeTab === 'image' ? '2px solid var(--accent-blue)' : '2px solid transparent',
              display: 'flex',
              alignItems: 'center',
              justify-content: 'center',
              gap: '6px',
              transition: 'all 0.2s ease',
            }}
          >
            <ImageIcon size={14} />
            <span>Search by Image</span>
          </button>
        </div>

        <form onSubmit={handleSearch} style={{ padding: '20px' }}>
          
          {/* Main Input Tab Content */}
          {activeTab === 'text' ? (
            <div style={{ marginBottom: '16px' }}>
              <label style={{ display: 'block', fontSize: '11px', fontWeight: 600, color: 'var(--text-secondary)', textTransform: 'uppercase', marginBottom: '6px' }}>
                Deskripsikan Wajah
              </label>
              <div style={{ position: 'relative' }}>
                <input
                  type="text"
                  placeholder="Contoh: pria berkacamata, wanita bahagia, ekspresi marah..."
                  value={textQuery}
                  onChange={(e) => setTextQuery(e.target.value)}
                  disabled={loading}
                  style={{
                    width: '100%',
                    padding: '10px 12px 10px 36px',
                    borderRadius: '8px',
                    border: '1px solid var(--border-color)',
                    background: 'var(--bg-primary)',
                    color: 'var(--text-primary)',
                    fontSize: '13px',
                    outline: 'none',
                  }}
                />
                <Search size={15} style={{ position: 'absolute', left: '12px', top: '12px', color: 'var(--text-muted)' }} />
              </div>
            </div>
          ) : (
            <div style={{ marginBottom: '16px' }}>
              <label style={{ display: 'block', fontSize: '11px', fontWeight: 600, color: 'var(--text-secondary)', textTransform: 'uppercase', marginBottom: '6px' }}>
                Unggah Foto Referensi
              </label>
              
              <input
                type="file"
                accept="image/*"
                ref={fileInputRef}
                onChange={handleFileChange}
                style={{ display: 'none' }}
              />

              {!previewUrl ? (
                <div
                  onDragOver={handleDragOver}
                  onDrop={handleDrop}
                  onClick={triggerFileSelect}
                  style={{
                    border: '2px dashed var(--border-color)',
                    borderRadius: '8px',
                    padding: '24px',
                    textAlign: 'center',
                    cursor: 'pointer',
                    background: 'var(--bg-primary)',
                    transition: 'border-color 0.2s ease',
                  }}
                  onMouseEnter={(e) => e.currentTarget.style.borderColor = 'var(--accent-blue)'}
                  onMouseLeave={(e) => e.currentTarget.style.borderColor = 'var(--border-color)'}
                >
                  <Upload size={24} style={{ color: 'var(--text-muted)', marginBottom: '8px' }} />
                  <p style={{ margin: '0 0 4px', fontSize: '12px', fontWeight: 600, color: 'var(--text-primary)' }}>
                    Seret gambar ke sini, atau klik untuk memilih file
                  </p>
                  <span style={{ fontSize: '10px', color: 'var(--text-muted)' }}>
                    Mendukung JPG, PNG, atau WEBP
                  </span>
                </div>
              ) : (
                <div style={{ display: 'flex', alignItems: 'center', gap: '12px', padding: '10px', border: '1px solid var(--border-color)', borderRadius: '8px', background: 'var(--bg-primary)' }}>
                  <img
                    src={previewUrl}
                    alt="Preview"
                    style={{ width: '56px', height: '56px', borderRadius: '6px', objectFit: 'cover', background: '#000' }}
                  />
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <p style={{ margin: 0, fontSize: '12px', fontWeight: 600, color: 'var(--text-primary)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                      {selectedFile?.name}
                    </p>
                    <span style={{ fontSize: '10px', color: 'var(--text-muted)' }}>
                      {selectedFile ? `${(selectedFile.size / 1024).toFixed(0)} KB` : ''}
                    </span>
                  </div>
                  <button
                    type="button"
                    onClick={() => { setSelectedFile(null); setPreviewUrl(null); }}
                    style={{ background: 'none', border: 'none', color: '#EF4444', cursor: 'pointer', padding: '6px' }}
                  >
                    Hapus
                  </button>
                </div>
              )}
            </div>
          )}

          {/* Config sliders */}
          <div style={{ padding: '14px', background: 'var(--bg-primary)', borderRadius: '8px', border: '1px solid var(--border-color)', marginBottom: '16px' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '6px', marginBottom: '12px', borderBottom: '1px solid var(--border-color)', paddingBottom: '6px' }}>
              <Sliders size={13} style={{ color: 'var(--accent-blue)' }} />
              <span style={{ fontSize: '11px', fontWeight: 700, color: 'var(--text-primary)', textTransform: 'uppercase', letterSpacing: '0.5px' }}>
                Konfigurasi Pencarian
              </span>
            </div>

            {/* Threshold */}
            <div style={{ marginBottom: '12px' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '11px', fontWeight: 500, color: 'var(--text-secondary)', marginBottom: '4px' }}>
                <span>Min Similarity</span>
                <span style={{ fontFamily: 'monospace', fontWeight: 600, color: 'var(--accent-blue)' }}>{(similarity * 100).toFixed(0)}%</span>
              </div>
              <input
                type="range"
                min="0.05"
                max="0.40"
                step="0.01"
                value={similarity}
                onChange={(e) => setSimilarity(parseFloat(e.target.value))}
                style={{ width: '100%', height: '4px', cursor: 'pointer' }}
              />
            </div>

            {/* Limit */}
            <div>
              <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '11px', fontWeight: 500, color: 'var(--text-secondary)', marginBottom: '4px' }}>
                <span>Max Results</span>
                <span style={{ fontFamily: 'monospace', fontWeight: 600, color: 'var(--text-secondary)' }}>{limit}</span>
              </div>
              <input
                type="range"
                min="5"
                max="50"
                step="5"
                value={limit}
                onChange={(e) => setLimit(parseInt(e.target.value))}
                style={{ width: '100%', height: '4px', cursor: 'pointer' }}
              />
            </div>
          </div>

          {/* Error Message */}
          {error && (
            <div style={{ padding: '8px 12px', background: '#FEF2F2', border: '1px solid #FEE2E2', borderRadius: '6px', color: '#991B1B', fontSize: '12px', marginBottom: '16px' }}>
              ⚠️ {error}
            </div>
          )}

          {/* Action buttons */}
          <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '8px' }}>
            <button
              type="button"
              onClick={onClose}
              disabled={loading}
              className="snap-filters__btn snap-filters__btn--secondary"
              style={{ padding: '8px 16px', fontSize: '12px', fontWeight: 600 }}
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={loading}
              className="snap-filters__btn snap-filters__btn--primary"
              style={{
                padding: '8px 16px',
                fontSize: '12px',
                fontWeight: 600,
                display: 'flex',
                alignItems: 'center',
                gap: '6px',
              }}
            >
              {loading ? (
                <>
                  <div className="snap-filters__spinner" style={{ width: '12px', height: '12px' }} />
                  <span>Searching...</span>
                </>
              ) : (
                <>
                  <Play size={12} fill="white" />
                  <span>Cari</span>
                </>
              )}
            </button>
          </div>

        </form>
      </div>
    </div>
  );
}
