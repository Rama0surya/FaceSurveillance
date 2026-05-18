/**
 * AnalyticsPage — Full analytics dashboard page.
 *
 * Features:
 *   - Date range picker + camera selector + Apply Filter button
 *   - 6 chart components in 2-column grid
 *   - Paginated detection table
 *   - Export CSV / Export PDF buttons
 *
 * Uses mock data when the API is unavailable for development.
 */

import { useState, useEffect, useMemo, useCallback } from 'react';
import {
  BarChart3,
  Calendar,
  Filter,
  Download,
  FileText,
  RefreshCw,
} from 'lucide-react';
import { useCameraStore } from '@/store/cameraStore';

import TrafficChart, { type TrafficChartData } from './TrafficChart';
import GenderPieChart from './GenderPieChart';
import EmotionBarChart from './EmotionBarChart';
import AgeDonutChart from './AgeDonutChart';
import WeeklyTrendChart, { type WeeklyDataPoint } from './WeeklyTrendChart';
import HeatmapGrid, { type HeatmapCell } from './HeatmapGrid';
import DetectionTable, { type DetectionRow } from './DetectionTable';

const API_BASE = import.meta.env.VITE_API_URL ?? 'http://localhost:8000';

/* ------------------------------------------------------------------ */
/* Mock data generators (used when backend is offline)                  */
/* ------------------------------------------------------------------ */

function generateMockHourly(): TrafficChartData[] {
  return Array.from({ length: 24 }, (_, h) => ({
    hour: h,
    total: Math.floor(Math.random() * 60) + (h >= 8 && h <= 18 ? 30 : 5),
  }));
}

function generateMockWeekly(): WeeklyDataPoint[] {
  const days = ['Min', 'Sen', 'Sel', 'Rab', 'Kam', 'Jum', 'Sab'];
  const now = new Date();
  return Array.from({ length: 7 }, (_, i) => {
    const d = new Date(now);
    d.setDate(d.getDate() - (6 - i));
    return {
      day: days[d.getDay()],
      fullDate: d.toISOString().slice(0, 10),
      total: Math.floor(Math.random() * 200) + 80,
    };
  });
}

function generateMockHeatmap(): HeatmapCell[] {
  const cells: HeatmapCell[] = [];
  for (let day = 0; day < 7; day++) {
    for (let hour = 0; hour < 24; hour++) {
      cells.push({
        day,
        hour,
        value: Math.floor(
          Math.random() * 40 * (hour >= 8 && hour <= 18 ? 2.5 : 0.5),
        ),
      });
    }
  }
  return cells;
}

function generateMockDetections(count: number): DetectionRow[] {
  const cameras = ['Lobby Utama', 'Pintu Masuk', 'Area Parkir', 'Lantai 2'];
  const genders = ['Man', 'Woman'];
  const emotions = ['happy', 'sad', 'angry', 'neutral', 'fear'];
  const ageGroups = ['Anak', 'Remaja', 'Dewasa', 'Lansia'];
  const rows: DetectionRow[] = [];
  const now = Date.now();
  for (let i = 0; i < count; i++) {
    const ageGroup = ageGroups[Math.floor(Math.random() * ageGroups.length)];
    let age = 30;
    if (ageGroup === 'Anak') age = Math.floor(Math.random() * 8) + 4;
    else if (ageGroup === 'Remaja') age = Math.floor(Math.random() * 7) + 13;
    else if (ageGroup === 'Dewasa') age = Math.floor(Math.random() * 30) + 20;
    else age = Math.floor(Math.random() * 20) + 55;
    rows.push({
      id: `det-${i}`,
      timestamp: new Date(now - i * 120000 - Math.random() * 60000).toISOString(),
      camera: cameras[Math.floor(Math.random() * cameras.length)],
      gender: genders[Math.floor(Math.random() * genders.length)],
      emotion: emotions[Math.floor(Math.random() * emotions.length)],
      age,
      age_group: ageGroup,
      snapshot_url: '',
    });
  }
  return rows;
}

/* ------------------------------------------------------------------ */
/* Component                                                            */
/* ------------------------------------------------------------------ */

export default function AnalyticsPage() {
  const cameras = useCameraStore((s) => s.cameras);

  /* ---- Filter state ---- */
  const today = new Date().toISOString().slice(0, 10);
  const weekAgo = new Date(Date.now() - 7 * 86400000).toISOString().slice(0, 10);

  const [startDate, setStartDate] = useState(weekAgo);
  const [endDate, setEndDate] = useState(today);
  const [selectedCamera, setSelectedCamera] = useState('all');
  const [loading, setLoading] = useState(false);

  /* ---- Data state ---- */
  const [hourlyData, setHourlyData] = useState<TrafficChartData[]>([]);
  const [male, setMale] = useState(0);
  const [female, setFemale] = useState(0);
  const [emotions, setEmotions] = useState({ happy: 0, sad: 0, angry: 0, neutral: 0, fear: 0 });
  const [ages, setAges] = useState({ child: 0, teen: 0, adult: 0, elderly: 0 });
  const [weeklyData, setWeeklyData] = useState<WeeklyDataPoint[]>([]);
  const [heatmapData, setHeatmapData] = useState<HeatmapCell[]>([]);
  const [detections, setDetections] = useState<DetectionRow[]>([]);

  /* ---- Fetch analytics data ---- */
  const fetchData = useCallback(async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams();
      if (selectedCamera !== 'all') params.set('camera_id', selectedCamera);
      params.set('start', startDate);
      params.set('end', endDate);

      // Try fetching from backend
      const res = await fetch(`${API_BASE}/api/stats/today?${params}`);
      if (res.ok) {
        const stats = await res.json();
        setMale(stats.male ?? 0);
        setFemale(stats.female ?? 0);
        setEmotions({
          happy: stats.emotions?.happy ?? 0,
          sad: stats.emotions?.sad ?? 0,
          angry: stats.emotions?.angry ?? 0,
          neutral: stats.emotions?.neutral ?? 0,
          fear: stats.emotions?.fear ?? 0,
        });
        setAges({
          child: stats.ages?.child ?? 0,
          teen: stats.ages?.teen ?? 0,
          adult: stats.ages?.adult ?? 0,
          elderly: stats.ages?.elderly ?? 0,
        });
      } else {
        throw new Error('API error');
      }

      // Fetch hourly
      const hRes = await fetch(`${API_BASE}/api/stats/hourly?${params}`);
      if (hRes.ok) {
        const hJson = await hRes.json();
        setHourlyData(hJson.data ?? []);
      }

      // Fetch detections
      const dParams = new URLSearchParams(params);
      dParams.set('limit', '200');
      const dRes = await fetch(`${API_BASE}/api/snapshots?${dParams}`);
      if (dRes.ok) {
        const dJson = await dRes.json();
        setDetections(
          (dJson.data ?? []).map((s: Record<string, unknown>) => ({
            id: s.id ?? s.detection_id,
            timestamp: s.timestamp,
            camera: s.camera_name ?? 'Unknown',
            gender: s.gender ?? 'Unknown',
            emotion: s.emotion ?? 'neutral',
            age: s.age ?? 0,
            age_group: s.age_group ?? '-',
            snapshot_url: s.url ?? '',
          })),
        );
      }
    } catch {
      // Fallback to mock data
      setHourlyData(generateMockHourly());
      setMale(Math.floor(Math.random() * 120) + 50);
      setFemale(Math.floor(Math.random() * 100) + 40);
      setEmotions({
        happy: Math.floor(Math.random() * 80) + 20,
        sad: Math.floor(Math.random() * 30) + 5,
        angry: Math.floor(Math.random() * 20) + 3,
        neutral: Math.floor(Math.random() * 60) + 30,
        fear: Math.floor(Math.random() * 15) + 2,
      });
      setAges({
        child: Math.floor(Math.random() * 15) + 3,
        teen: Math.floor(Math.random() * 25) + 10,
        adult: Math.floor(Math.random() * 100) + 50,
        elderly: Math.floor(Math.random() * 20) + 5,
      });
      setWeeklyData(generateMockWeekly());
      setHeatmapData(generateMockHeatmap());
      setDetections(generateMockDetections(85));
    }
    setLoading(false);
  }, [selectedCamera, startDate, endDate]);

  // Generate weekly + heatmap from mock (these rarely come from a simple API)
  useEffect(() => {
    if (weeklyData.length === 0) setWeeklyData(generateMockWeekly());
    if (heatmapData.length === 0) setHeatmapData(generateMockHeatmap());
  }, []);

  // Fetch on mount
  useEffect(() => {
    fetchData();
  }, []);

  /* ---- Export CSV ---- */
  function exportCSV() {
    if (detections.length === 0) return;
    const headers = ['Timestamp', 'Kamera', 'Gender', 'Emosi', 'Usia', 'Kelompok Usia'];
    const rows = detections.map((d) => [
      d.timestamp,
      d.camera,
      d.gender,
      d.emotion,
      String(d.age),
      d.age_group,
    ]);
    const csv = [headers, ...rows].map((r) => r.join(',')).join('\n');
    const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `analytics_${startDate}_${endDate}.csv`;
    link.click();
    URL.revokeObjectURL(url);
  }

  /* ---- Summary stats ---- */
  const totalDetections = useMemo(
    () => hourlyData.reduce((s, h) => s + h.total, 0),
    [hourlyData],
  );

  return (
    <div className="analytics-page">
      {/* Page Header */}
      <div className="analytics-page__header">
        <div className="analytics-page__header-left">
          <BarChart3 size={24} className="analytics-page__header-icon" />
          <div>
            <h1 className="analytics-page__title">Analytics</h1>
            <p className="analytics-page__subtitle">
              Analisis deteksi wajah berdasarkan waktu, gender, emosi, dan usia
            </p>
          </div>
        </div>

        {/* Export Buttons */}
        <div className="analytics-page__header-right">
          <button
            id="btn-export-csv"
            className="analytics-page__btn analytics-page__btn--secondary"
            onClick={exportCSV}
            disabled={detections.length === 0}
          >
            <Download size={14} />
            Export CSV
          </button>
          <button
            id="btn-export-pdf"
            className="analytics-page__btn analytics-page__btn--secondary"
            onClick={() => alert('Export PDF — fitur akan segera hadir.')}
          >
            <FileText size={14} />
            Export PDF
          </button>
        </div>
      </div>

      {/* Filters */}
      <div className="analytics-filters">
        <div className="analytics-filters__group">
          <label className="analytics-filters__label">
            <Calendar size={14} />
            Mulai
          </label>
          <input
            id="filter-start-date"
            type="date"
            className="analytics-filters__input"
            value={startDate}
            onChange={(e) => setStartDate(e.target.value)}
          />
        </div>
        <div className="analytics-filters__group">
          <label className="analytics-filters__label">
            <Calendar size={14} />
            Akhir
          </label>
          <input
            id="filter-end-date"
            type="date"
            className="analytics-filters__input"
            value={endDate}
            onChange={(e) => setEndDate(e.target.value)}
          />
        </div>
        <div className="analytics-filters__group">
          <label className="analytics-filters__label">
            <Filter size={14} />
            Kamera
          </label>
          <select
            id="filter-camera"
            className="analytics-filters__select"
            value={selectedCamera}
            onChange={(e) => setSelectedCamera(e.target.value)}
          >
            <option value="all">Semua Kamera</option>
            {cameras.map((cam) => (
              <option key={cam.id} value={cam.id}>
                {cam.name}
              </option>
            ))}
          </select>
        </div>
        <button
          id="btn-apply-filter"
          className="analytics-page__btn analytics-page__btn--primary"
          onClick={fetchData}
          disabled={loading}
        >
          {loading ? (
            <RefreshCw size={14} className="analytics-spin" />
          ) : (
            <Filter size={14} />
          )}
          {loading ? 'Memuat...' : 'Apply Filter'}
        </button>
      </div>

      {/* Summary cards */}
      <div className="analytics-summary">
        <div className="analytics-summary__card">
          <div className="analytics-summary__value">{totalDetections}</div>
          <div className="analytics-summary__label">Total Deteksi</div>
        </div>
        <div className="analytics-summary__card">
          <div className="analytics-summary__value">{male + female}</div>
          <div className="analytics-summary__label">Total Orang</div>
        </div>
        <div className="analytics-summary__card analytics-summary__card--male">
          <div className="analytics-summary__value">{male}</div>
          <div className="analytics-summary__label">Pria</div>
        </div>
        <div className="analytics-summary__card analytics-summary__card--female">
          <div className="analytics-summary__value">{female}</div>
          <div className="analytics-summary__label">Wanita</div>
        </div>
      </div>

      {/* Charts — 2 column grid */}
      <div className="analytics-grid">
        <TrafficChart data={hourlyData} />
        <GenderPieChart male={male} female={female} />
        <EmotionBarChart emotions={emotions} />
        <AgeDonutChart ages={ages} />
        <WeeklyTrendChart data={weeklyData} />
        <div /> {/* spacer for grid alignment */}
      </div>

      {/* Heatmap (full-width) */}
      <HeatmapGrid data={heatmapData} />

      {/* Detection Table */}
      <DetectionTable data={detections} />
    </div>
  );
}
