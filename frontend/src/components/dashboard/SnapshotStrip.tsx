/**
 * SnapshotStrip — grid of recent face snapshots fetched from API,
 * with emotion filter pills, date picker, and "Search by Image" button.
 */

import { useState, useEffect, useCallback } from 'react';
import { useCameraStore } from '@/store/cameraStore';
import { fetchSnapshots } from '@/lib/api';
import SnapshotModal from './SnapshotModal';
import type { Snapshot } from '@/store/cameraStore';
import { Search, Calendar } from 'lucide-react';

type FilterKey = 'all' | 'angry' | 'sad' | 'happy' | 'fear' | 'neutral';

const FILTERS: { key: FilterKey; label: string }[] = [
  { key: 'all', label: 'All' },
  { key: 'angry', label: 'Marah' },
  { key: 'sad', label: 'Sedih' },
  { key: 'happy', label: 'Senang' },
  { key: 'fear', label: 'Takut' },
  { key: 'neutral', label: 'Netral' },
];

export default function SnapshotStrip() {
  const activeCamera = useCameraStore((s) => s.activeCamera);
  const storeSnapshots = useCameraStore((s) => s.snapshots);
  const setSnapshots = useCameraStore((s) => s.setSnapshots);

  const [filter, setFilter] = useState<FilterKey>('all');
  const [selected, setSelected] = useState<Snapshot | null>(null);
  const [date, setDate] = useState(() => new Date().toISOString().slice(0, 10));
  const [loading, setLoading] = useState(false);

  /**
   * Fetch snapshots from API based on current filters.
   */
  const loadSnapshots = useCallback(
    async (emotion?: string) => {
      if (!activeCamera) return;
      setLoading(true);
      try {
        const result = await fetchSnapshots({
          cameraId: activeCamera.id,
          date,
          emotion: emotion && emotion !== 'all' ? emotion : undefined,
          limit: 20,
        });
        if (result.data) {
          const mapped: Snapshot[] = result.data.map((row) => ({
            id: row.id,
            camera_id: row.camera_id ?? activeCamera.id,
            detection_id: row.detection_id ?? row.id,
            url: row.url,
            gender: row.gender,
            emotion: row.emotion,
            age: row.age,
            age_group: row.age_group,
            camera_name: row.camera_name ?? activeCamera.name,
            timestamp: row.timestamp,
          }));
          setSnapshots(mapped);
        }
      } catch {
        // API not available — keep store snapshots (from WebSocket)
      } finally {
        setLoading(false);
      }
    },
    [activeCamera, date, setSnapshots],
  );

  // Fetch on mount and when camera / date changes
  useEffect(() => {
    loadSnapshots(filter);
  }, [activeCamera?.id, date]); // eslint-disable-line react-hooks/exhaustive-deps

  // Handle filter pill click
  function handleFilterClick(key: FilterKey) {
    setFilter(key);
    loadSnapshots(key);
  }

  // Display store snapshots (may be enriched by WebSocket in real-time)
  const displayed =
    filter === 'all'
      ? storeSnapshots.slice(0, 20)
      : storeSnapshots.filter((s) => s.emotion === filter).slice(0, 20);

  return (
    <>
      <div className="snapshot-strip" id="snapshot-strip">
        {/* Header row: title + date picker + search */}
        <div className="snapshot-strip__header">
          <span className="snapshot-strip__title">📸 Face Capture</span>

          <div className="snapshot-strip__controls">
            {/* Date picker */}
            <div className="snapshot-strip__date-picker">
              <Calendar size={12} />
              <input
                type="date"
                value={date}
                onChange={(e) => setDate(e.target.value)}
                className="snapshot-strip__date-input"
                id="snapshot-date-picker"
              />
            </div>

            {/* Search by Image (placeholder) */}
            <button
              className="snapshot-strip__search-btn"
              title="Search by Image (coming soon)"
              id="search-by-image-btn"
              onClick={() => alert('🔍 Fitur Search by Image akan segera hadir!')}
            >
              <Search size={13} />
              <span>Search by Image</span>
            </button>
          </div>
        </div>

        {/* Filter pills */}
        <div className="snapshot-strip__filters">
          {FILTERS.map((f) => (
            <button
              key={f.key}
              className={`snapshot-strip__pill ${filter === f.key ? 'snapshot-strip__pill--active' : ''}`}
              onClick={() => handleFilterClick(f.key)}
            >
              {f.label}
            </button>
          ))}
        </div>

        {/* Loading indicator */}
        {loading && (
          <div className="snapshot-strip__loading">
            <span className="snapshot-strip__spinner" />
            <span>Loading…</span>
          </div>
        )}

        {/* Thumbnail grid */}
        <div className="snapshot-strip__row">
          {!loading && displayed.length === 0 && (
            <span className="snapshot-strip__empty">
              No snapshots yet
            </span>
          )}
          {displayed.map((snap) => (
            <button
              key={snap.id}
              className="snapshot-strip__thumb"
              onClick={() => setSelected(snap)}
              title={`${snap.gender} · ${snap.emotion}`}
            >
              <img src={snap.url} alt="face" draggable={false} />
              <span
                className="snapshot-strip__emotion-dot"
                style={{ backgroundColor: emotionColor(snap.emotion) }}
              />
            </button>
          ))}
        </div>
      </div>

      {/* Modal */}
      {selected && (
        <SnapshotModal
          snapshot={selected}
          onClose={() => setSelected(null)}
        />
      )}
    </>
  );
}

function emotionColor(emotion: string): string {
  const map: Record<string, string> = {
    happy: '#22c55e',
    angry: '#ef4444',
    neutral: '#3b82f6',
    sad: '#a855f7',
    fear: '#eab308',
  };
  return map[emotion] ?? '#94a3b8';
}
