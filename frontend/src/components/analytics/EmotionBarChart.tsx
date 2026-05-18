/**
 * EmotionBarChart — Horizontal bar chart showing 5 emotions:
 * Senang (green), Sedih (purple), Marah (red), Netral (blue), Takut (yellow).
 */

import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Cell,
} from 'recharts';

export interface EmotionData {
  name: string;
  value: number;
  color: string;
}

interface Props {
  emotions: {
    happy: number;
    sad: number;
    angry: number;
    neutral: number;
    fear: number;
  };
}

export default function EmotionBarChart({ emotions }: Props) {
  const data: EmotionData[] = [
    { name: 'Senang', value: emotions.happy, color: '#22c55e' },
    { name: 'Sedih', value: emotions.sad, color: '#a855f7' },
    { name: 'Marah', value: emotions.angry, color: '#ef4444' },
    { name: 'Netral', value: emotions.neutral, color: '#3b82f6' },
    { name: 'Takut', value: emotions.fear, color: '#eab308' },
  ];

  return (
    <div className="analytics-card">
      <div className="analytics-card__header">
        <span className="analytics-card__dot analytics-card__dot--green" />
        Distribusi Emosi
      </div>
      <div className="analytics-card__body">
        <ResponsiveContainer width="100%" height={260}>
          <BarChart
            data={data}
            layout="vertical"
            margin={{ top: 8, right: 24, left: 8, bottom: 0 }}
          >
            <CartesianGrid strokeDasharray="3 3" stroke="#E5E7EB" horizontal={false} />
            <XAxis
              type="number"
              tick={{ fontSize: 11, fill: '#6B7280' }}
              axisLine={false}
              tickLine={false}
            />
            <YAxis
              type="category"
              dataKey="name"
              tick={{ fontSize: 12, fill: '#374151', fontWeight: 500 }}
              axisLine={false}
              tickLine={false}
              width={54}
            />
            <Tooltip
              contentStyle={{
                background: '#fff',
                border: '1px solid #E5E7EB',
                borderRadius: 8,
                fontSize: 12,
                boxShadow: '0 4px 12px rgba(0,0,0,0.08)',
              }}
              formatter={(value: number) => [value, 'Deteksi']}
              cursor={{ fill: 'rgba(37, 99, 235, 0.04)' }}
            />
            <Bar dataKey="value" radius={[0, 6, 6, 0]} maxBarSize={28}>
              {data.map((entry, i) => (
                <Cell key={i} fill={entry.color} />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
