/**
 * RightPanel — right column (280px):
 *   - Gender stats (Women/Men cards)
 *   - Emotion stats (Satisfied/Neutral/Unsatisfied)
 *   - Age donut chart
 *   - Crowd Estimates meter
 */

import { useCameraStore } from '@/store/cameraStore';
import {
  PieChart,
  Pie,
  Cell,
  ResponsiveContainer,
  Tooltip,
} from 'recharts';
import { User, UserCircle, Activity } from 'lucide-react';

/* ---- Age donut colors ---- */
const AGE_COLORS = ['#2563EB', '#8b5cf6', '#f97316', '#ec4899'];
const AGE_LABELS: Record<string, string> = {
  child: 'Anak',
  teen: 'Remaja',
  adult: 'Dewasa',
  elderly: 'Lansia',
};

const CROWD_CAPACITY = 50;

/* ---- Emotion color map ---- */
const EMOTION_COLORS: Record<string, string> = {
  happy: '#22c55e',
  angry: '#ef4444',
  neutral: '#3b82f6',
  sad: '#a855f7',
  fear: '#eab308',
};

const EMOTION_LABELS: Record<string, string> = {
  happy: 'Senang',
  angry: 'Marah',
  neutral: 'Netral',
  sad: 'Sedih',
  fear: 'Takut',
};

export default function RightPanel() {
  const { todayStats, currentFaces } = useCameraStore();

  const ageData = Object.entries(todayStats.ages).map(([key, value]) => ({
    name: AGE_LABELS[key] ?? key,
    value,
  }));

  const totalEmotions = Object.values(todayStats.emotions).reduce(
    (a, b) => a + b,
    0,
  );

  const crowdPct = Math.min(
    (currentFaces.length / CROWD_CAPACITY) * 100,
    100,
  );
  const crowdLevel =
    crowdPct < 40 ? 'low' : crowdPct < 70 ? 'medium' : 'high';

  return (
    <aside className="right-panel">
      {/* ---- Gender Stats ---- */}
      <div className="stats-card">
        <div className="stats-card__header">
          <UserCircle size={14} />
          <span>Gender</span>
        </div>
        <div className="gender-grid">
          <div className="gender-col">
            <User size={20} className="gender-icon gender-icon--female" />
            <span className="gender-label">Wanita</span>
            <span className="gender-value">{todayStats.female}</span>
          </div>
          <div className="gender-col">
            <User size={20} className="gender-icon gender-icon--male" />
            <span className="gender-label">Pria</span>
            <span className="gender-value">{todayStats.male}</span>
          </div>
        </div>
        {/* Mini ratio bar */}
        <div className="gender-bar">
          <div
            className="gender-bar__female"
            style={{
              width: `${todayStats.total > 0 ? (todayStats.female / todayStats.total) * 100 : 50}%`,
            }}
          />
          <div
            className="gender-bar__male"
            style={{
              width: `${todayStats.total > 0 ? (todayStats.male / todayStats.total) * 100 : 50}%`,
            }}
          />
        </div>
      </div>

      {/* ---- Emotion Bars ---- */}
      <div className="stats-card">
        <div className="stats-card__header">
          <span>🎭</span>
          <span>Emosi</span>
        </div>
        <div className="emotion-bars">
          {Object.entries(todayStats.emotions).map(([emotion, count]) => {
            const pct = totalEmotions > 0 ? (count / totalEmotions) * 100 : 0;
            return (
              <div key={emotion} className="emotion-row">
                <span className="emotion-row__label">
                  {EMOTION_LABELS[emotion] ?? emotion}
                </span>
                <div className="emotion-row__track">
                  <div
                    className="emotion-row__fill"
                    style={{
                      width: `${pct}%`,
                      backgroundColor: EMOTION_COLORS[emotion],
                    }}
                  />
                </div>
                <span className="emotion-row__count">{count}</span>
              </div>
            );
          })}
        </div>
      </div>

      {/* ---- Age Donut ---- */}
      <div className="stats-card">
        <div className="stats-card__header">
          <span>👤</span>
          <span>Usia</span>
        </div>
        <div className="age-donut">
          <ResponsiveContainer width="100%" height={130}>
            <PieChart>
              <Pie
                data={ageData}
                cx="50%"
                cy="50%"
                innerRadius={35}
                outerRadius={55}
                paddingAngle={3}
                dataKey="value"
                stroke="none"
              >
                {ageData.map((_, i) => (
                  <Cell key={i} fill={AGE_COLORS[i % AGE_COLORS.length]} />
                ))}
              </Pie>
              <Tooltip
                contentStyle={{
                  background: '#fff',
                  border: '1px solid #E5E7EB',
                  borderRadius: 6,
                  fontSize: 11,
                  color: '#111827',
                  boxShadow: '0 2px 8px rgba(0,0,0,0.08)',
                }}
              />
            </PieChart>
          </ResponsiveContainer>
          <div className="age-legend">
            {ageData.map((entry, i) => (
              <div key={entry.name} className="age-legend__item">
                <span
                  className="age-legend__dot"
                  style={{ backgroundColor: AGE_COLORS[i] }}
                />
                <span className="age-legend__label">{entry.name}</span>
                <span className="age-legend__value">{entry.value}</span>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* ---- Crowd Estimates ---- */}
      <div className="stats-card">
        <div className="stats-card__header">
          <Activity size={14} />
          <span>Crowd Estimates</span>
        </div>
        <div className="crowd-meter">
          <div className="crowd-meter__bar">
            <div
              className={`crowd-meter__fill crowd-meter__fill--${crowdLevel}`}
              style={{ height: `${crowdPct}%` }}
            />
          </div>
          <div className="crowd-meter__info">
            <span className="crowd-meter__value">{currentFaces.length}</span>
            <span className="crowd-meter__label">/ {CROWD_CAPACITY}</span>
          </div>
        </div>
      </div>
    </aside>
  );
}
