/**
 * StatsPanel — left column top cards:
 *   - "Today's People" counter with sparkline
 *   - "Today's Traffic" bar chart
 *   - "Comparison Traffic" card (Today vs Yesterday with % change)
 */

import { useCameraStore } from '@/store/cameraStore';
import {
  AreaChart,
  Area,
  Tooltip,
  ResponsiveContainer,
} from 'recharts';
import { Users, TrendingUp, TrendingDown, Minus } from 'lucide-react';

export default function StatsPanel() {
  const { todayStats, hourlyData, comparisonData } = useCameraStore();

  const changePct = comparisonData?.change_pct ?? 0;
  const isUp = changePct > 0;
  const isDown = changePct < 0;

  return (
    <>
      {/* ---- Today's People Counter ---- */}
      <div className="stats-card">
        <div className="stats-card__header">
          <Users size={14} />
          <span>Today's People</span>
        </div>
        <div className="stats-card__big-number">{todayStats.total}</div>

        {/* Sparkline */}
        <div className="stats-card__sparkline">
          <ResponsiveContainer width="100%" height={50}>
            <AreaChart data={hourlyData.length > 0 ? hourlyData : defaultHourly()}>
              <defs>
                <linearGradient id="sparkGrad" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="#2563EB" stopOpacity={0.3} />
                  <stop offset="100%" stopColor="#2563EB" stopOpacity={0.02} />
                </linearGradient>
              </defs>
              <Tooltip
                contentStyle={{
                  background: '#fff',
                  border: '1px solid #E5E7EB',
                  borderRadius: 6,
                  fontSize: 11,
                  color: '#111827',
                  boxShadow: '0 2px 8px rgba(0,0,0,0.08)',
                }}
                labelFormatter={(l) => `${l}:00`}
              />
              <Area
                type="monotone"
                dataKey="total"
                stroke="#2563EB"
                fill="url(#sparkGrad)"
                strokeWidth={1.5}
              />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      </div>

      {/* ---- Today's Traffic Summary ---- */}
      <div className="stats-card">
        <div className="stats-card__header">
          <span>📊</span>
          <span>Today's Traffic</span>
        </div>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-end', gap: '4px', height: '60px', paddingTop: '4px' }}>
          {(hourlyData.length > 0 ? hourlyData : defaultHourly()).slice(6, 22).map((h, i) => {
            const maxVal = Math.max(...(hourlyData.length > 0 ? hourlyData : defaultHourly()).map(d => d.total), 1);
            const barHeight = Math.max((h.total / maxVal) * 50, 2);
            return (
              <div
                key={i}
                style={{
                  flex: 1,
                  display: 'flex',
                  flexDirection: 'column',
                  alignItems: 'center',
                  justifyContent: 'flex-end',
                  height: '100%',
                }}
              >
                <div
                  style={{
                    width: '100%',
                    maxWidth: '10px',
                    height: `${barHeight}px`,
                    background: '#2563EB',
                    borderRadius: '2px 2px 0 0',
                    transition: 'height 0.3s ease',
                    opacity: 0.75 + (h.total / maxVal) * 0.25,
                  }}
                />
              </div>
            );
          })}
        </div>
        <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: '4px' }}>
          <span style={{ fontSize: '9px', color: '#9CA3AF' }}>6h</span>
          <span style={{ fontSize: '9px', color: '#9CA3AF' }}>14h</span>
          <span style={{ fontSize: '9px', color: '#9CA3AF' }}>22h</span>
        </div>
      </div>

      {/* ---- Comparison Traffic Card ---- */}
      <div className="stats-card comparison-card" id="comparison-traffic-card">
        <div className="stats-card__header">
          {isUp ? <TrendingUp size={14} /> : isDown ? <TrendingDown size={14} /> : <Minus size={14} />}
          <span>Comparison Traffic</span>
        </div>
        <div className="comparison-card__body">
          <div className="comparison-card__row">
            <span className="comparison-card__label">Today</span>
            <span className="comparison-card__value">
              {comparisonData?.today?.total ?? todayStats.total}
            </span>
          </div>
          <div className="comparison-card__row">
            <span className="comparison-card__label">Yesterday</span>
            <span className="comparison-card__value comparison-card__value--muted">
              {comparisonData?.yesterday?.total ?? 0}
            </span>
          </div>
          <div className="comparison-card__divider" />
          <div
            className={`comparison-card__badge ${
              isUp
                ? 'comparison-card__badge--up'
                : isDown
                ? 'comparison-card__badge--down'
                : 'comparison-card__badge--neutral'
            }`}
          >
            {isUp ? <TrendingUp size={12} /> : isDown ? <TrendingDown size={12} /> : <Minus size={12} />}
            <span>
              {isUp ? '+' : ''}
              {changePct.toFixed(1)}%
            </span>
          </div>
        </div>
      </div>
    </>
  );
}

/* Default empty hourly data for sparkline */
function defaultHourly() {
  return Array.from({ length: 24 }, (_, i) => ({ hour: i, total: 0 }));
}
