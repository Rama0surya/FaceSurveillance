/**
 * TrafficChart — Daily traffic BarChart (hourly 00–23).
 * X axis: hour, Y axis: detection count.
 */

import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from 'recharts';

export interface TrafficChartData {
  hour: number;
  total: number;
}

interface Props {
  data: TrafficChartData[];
}

export default function TrafficChart({ data }: Props) {
  return (
    <div className="analytics-card">
      <div className="analytics-card__header">
        <span className="analytics-card__dot analytics-card__dot--blue" />
        Traffic Harian
      </div>
      <div className="analytics-card__body">
        <ResponsiveContainer width="100%" height={260}>
          <BarChart data={data} margin={{ top: 8, right: 8, left: -12, bottom: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#E5E7EB" vertical={false} />
            <XAxis
              dataKey="hour"
              tick={{ fontSize: 11, fill: '#6B7280' }}
              axisLine={{ stroke: '#E5E7EB' }}
              tickLine={false}
              tickFormatter={(v: number) => `${String(v).padStart(2, '0')}:00`}
              interval={2}
            />
            <YAxis
              tick={{ fontSize: 11, fill: '#6B7280' }}
              axisLine={false}
              tickLine={false}
            />
            <Tooltip
              contentStyle={{
                background: '#fff',
                border: '1px solid #E5E7EB',
                borderRadius: 8,
                fontSize: 12,
                boxShadow: '0 4px 12px rgba(0,0,0,0.08)',
              }}
              labelFormatter={(v: number) => `Jam ${String(v).padStart(2, '0')}:00`}
              formatter={(value: number) => [value, 'Deteksi']}
              cursor={{ fill: 'rgba(37, 99, 235, 0.06)' }}
            />
            <Bar
              dataKey="total"
              fill="#2563EB"
              radius={[4, 4, 0, 0]}
              maxBarSize={24}
            />
          </BarChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
