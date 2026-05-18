/**
 * HeatmapGrid — 7×24 heatmap grid.
 * Rows: days (Mon–Sun), Columns: hours (0–23).
 * Color intensity based on detection count.
 */

import { useMemo } from 'react';

export interface HeatmapCell {
  day: number;  // 0=Mon, 6=Sun
  hour: number; // 0–23
  value: number;
}

interface Props {
  data: HeatmapCell[];
}

const DAY_LABELS = ['Sen', 'Sel', 'Rab', 'Kam', 'Jum', 'Sab', 'Min'];

function getCellColor(value: number, max: number): string {
  if (max === 0 || value === 0) return '#F3F4F6';
  const ratio = value / max;
  if (ratio < 0.2) return '#DBEAFE';
  if (ratio < 0.4) return '#93C5FD';
  if (ratio < 0.6) return '#60A5FA';
  if (ratio < 0.8) return '#2563EB';
  return '#1D4ED8';
}

export default function HeatmapGrid({ data }: Props) {
  const { grid, max } = useMemo(() => {
    const g: number[][] = Array.from({ length: 7 }, () => Array(24).fill(0));
    let m = 0;
    data.forEach((cell) => {
      if (cell.day >= 0 && cell.day < 7 && cell.hour >= 0 && cell.hour < 24) {
        g[cell.day][cell.hour] = cell.value;
        if (cell.value > m) m = cell.value;
      }
    });
    return { grid: g, max: m };
  }, [data]);

  return (
    <div className="analytics-card analytics-card--wide">
      <div className="analytics-card__header">
        <span className="analytics-card__dot analytics-card__dot--blue" />
        Heatmap Jam Sibuk
      </div>
      <div className="analytics-card__body">
        <div className="heatmap">
          {/* Hour headers */}
          <div className="heatmap__row heatmap__row--header">
            <div className="heatmap__label" />
            {Array.from({ length: 24 }, (_, h) => (
              <div key={h} className="heatmap__hour-label">
                {h % 3 === 0 ? h : ''}
              </div>
            ))}
          </div>

          {/* Data rows */}
          {grid.map((row, dayIdx) => (
            <div key={dayIdx} className="heatmap__row">
              <div className="heatmap__label">{DAY_LABELS[dayIdx]}</div>
              {row.map((val, hourIdx) => (
                <div
                  key={hourIdx}
                  className="heatmap__cell"
                  style={{ backgroundColor: getCellColor(val, max) }}
                  title={`${DAY_LABELS[dayIdx]} ${String(hourIdx).padStart(2, '0')}:00 — ${val} deteksi`}
                />
              ))}
            </div>
          ))}

          {/* Legend */}
          <div className="heatmap__legend">
            <span className="heatmap__legend-label">Sedikit</span>
            <div className="heatmap__legend-scale">
              {['#F3F4F6', '#DBEAFE', '#93C5FD', '#60A5FA', '#2563EB', '#1D4ED8'].map(
                (c, i) => (
                  <div
                    key={i}
                    className="heatmap__legend-swatch"
                    style={{ backgroundColor: c }}
                  />
                ),
              )}
            </div>
            <span className="heatmap__legend-label">Banyak</span>
          </div>
        </div>
      </div>
    </div>
  );
}
