/**
 * DetectionTable — Paginated sortable table of recent detections.
 * Columns: timestamp, camera, gender, emotion, age, snapshot thumbnail.
 * 20 rows per page with pagination controls.
 */

import { useState, useMemo } from 'react';
import { ChevronUp, ChevronDown, ChevronLeft, ChevronRight } from 'lucide-react';

export interface DetectionRow {
  id: string;
  timestamp: string;
  camera: string;
  gender: string;
  emotion: string;
  age: number;
  age_group: string;
  snapshot_url: string;
}

interface Props {
  data: DetectionRow[];
}

type SortKey = 'timestamp' | 'camera' | 'gender' | 'emotion' | 'age';
type SortDir = 'asc' | 'desc';

const PAGE_SIZE = 20;

const EMOTION_LABELS: Record<string, string> = {
  happy: 'Senang',
  sad: 'Sedih',
  angry: 'Marah',
  neutral: 'Netral',
  fear: 'Takut',
};

const GENDER_LABELS: Record<string, string> = {
  Man: 'Pria',
  Woman: 'Wanita',
  Male: 'Pria',
  Female: 'Wanita',
};

const EMOTION_DOT_COLOR: Record<string, string> = {
  happy: '#22c55e',
  sad: '#a855f7',
  angry: '#ef4444',
  neutral: '#3b82f6',
  fear: '#eab308',
};

export default function DetectionTable({ data }: Props) {
  const [sortKey, setSortKey] = useState<SortKey>('timestamp');
  const [sortDir, setSortDir] = useState<SortDir>('desc');
  const [page, setPage] = useState(0);

  const sorted = useMemo(() => {
    const arr = [...data];
    arr.sort((a, b) => {
      let cmp = 0;
      switch (sortKey) {
        case 'timestamp':
          cmp = a.timestamp.localeCompare(b.timestamp);
          break;
        case 'camera':
          cmp = a.camera.localeCompare(b.camera);
          break;
        case 'gender':
          cmp = a.gender.localeCompare(b.gender);
          break;
        case 'emotion':
          cmp = a.emotion.localeCompare(b.emotion);
          break;
        case 'age':
          cmp = a.age - b.age;
          break;
      }
      return sortDir === 'asc' ? cmp : -cmp;
    });
    return arr;
  }, [data, sortKey, sortDir]);

  const totalPages = Math.max(1, Math.ceil(sorted.length / PAGE_SIZE));
  const paginated = sorted.slice(page * PAGE_SIZE, (page + 1) * PAGE_SIZE);

  function handleSort(key: SortKey) {
    if (sortKey === key) {
      setSortDir((d) => (d === 'asc' ? 'desc' : 'asc'));
    } else {
      setSortKey(key);
      setSortDir('desc');
    }
    setPage(0);
  }

  function SortIcon({ col }: { col: SortKey }) {
    if (sortKey !== col) return <ChevronUp size={12} style={{ opacity: 0.25 }} />;
    return sortDir === 'asc' ? (
      <ChevronUp size={12} />
    ) : (
      <ChevronDown size={12} />
    );
  }

  return (
    <div className="analytics-card analytics-card--wide analytics-card--table">
      <div className="analytics-card__header">
        <span className="analytics-card__dot analytics-card__dot--blue" />
        Data Deteksi Terbaru
      </div>
      <div className="det-table-wrapper">
        <table className="det-table">
          <thead>
            <tr>
              <th className="det-table__th det-table__th--snap">Snapshot</th>
              <th className="det-table__th" onClick={() => handleSort('timestamp')}>
                <span>Waktu</span> <SortIcon col="timestamp" />
              </th>
              <th className="det-table__th" onClick={() => handleSort('camera')}>
                <span>Kamera</span> <SortIcon col="camera" />
              </th>
              <th className="det-table__th" onClick={() => handleSort('gender')}>
                <span>Gender</span> <SortIcon col="gender" />
              </th>
              <th className="det-table__th" onClick={() => handleSort('emotion')}>
                <span>Emosi</span> <SortIcon col="emotion" />
              </th>
              <th className="det-table__th" onClick={() => handleSort('age')}>
                <span>Usia</span> <SortIcon col="age" />
              </th>
            </tr>
          </thead>
          <tbody>
            {paginated.length === 0 ? (
              <tr>
                <td colSpan={6} className="det-table__empty">
                  Belum ada data deteksi
                </td>
              </tr>
            ) : (
              paginated.map((row) => (
                <tr key={row.id} className="det-table__row">
                  <td className="det-table__td">
                    <div className="det-table__thumb">
                      {row.snapshot_url ? (
                        <img src={row.snapshot_url} alt="snap" />
                      ) : (
                        <div className="det-table__thumb-placeholder" />
                      )}
                    </div>
                  </td>
                  <td className="det-table__td det-table__td--mono">
                    {new Date(row.timestamp).toLocaleString('id-ID', {
                      day: '2-digit',
                      month: 'short',
                      hour: '2-digit',
                      minute: '2-digit',
                      second: '2-digit',
                    })}
                  </td>
                  <td className="det-table__td">{row.camera}</td>
                  <td className="det-table__td">
                    <span
                      className={`det-table__gender-badge ${
                        row.gender === 'Man' || row.gender === 'Male'
                          ? 'det-table__gender-badge--male'
                          : 'det-table__gender-badge--female'
                      }`}
                    >
                      {GENDER_LABELS[row.gender] ?? row.gender}
                    </span>
                  </td>
                  <td className="det-table__td">
                    <span className="det-table__emotion">
                      <span
                        className="det-table__emotion-dot"
                        style={{ background: EMOTION_DOT_COLOR[row.emotion] ?? '#9CA3AF' }}
                      />
                      {EMOTION_LABELS[row.emotion] ?? row.emotion}
                    </span>
                  </td>
                  <td className="det-table__td">
                    <span className="det-table__age-badge">
                      {row.age} <span className="det-table__age-group">({row.age_group})</span>
                    </span>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      {/* Pagination */}
      <div className="det-table__pagination">
        <span className="det-table__page-info">
          Halaman {page + 1} dari {totalPages} ({sorted.length} data)
        </span>
        <div className="det-table__page-btns">
          <button
            className="det-table__page-btn"
            disabled={page === 0}
            onClick={() => setPage((p) => p - 1)}
          >
            <ChevronLeft size={16} />
          </button>
          {/* Show max 5 page buttons */}
          {Array.from({ length: Math.min(5, totalPages) }, (_, i) => {
            let pn: number;
            if (totalPages <= 5) {
              pn = i;
            } else if (page < 3) {
              pn = i;
            } else if (page > totalPages - 4) {
              pn = totalPages - 5 + i;
            } else {
              pn = page - 2 + i;
            }
            return (
              <button
                key={pn}
                className={`det-table__page-btn ${page === pn ? 'det-table__page-btn--active' : ''}`}
                onClick={() => setPage(pn)}
              >
                {pn + 1}
              </button>
            );
          })}
          <button
            className="det-table__page-btn"
            disabled={page >= totalPages - 1}
            onClick={() => setPage((p) => p + 1)}
          >
            <ChevronRight size={16} />
          </button>
        </div>
      </div>
    </div>
  );
}
