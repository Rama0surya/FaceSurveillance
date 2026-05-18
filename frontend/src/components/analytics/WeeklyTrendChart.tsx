/**
 * WeeklyTrendChart — Line chart showing 7-day detection trend
 * with gradient area fill.
 */

import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from 'recharts';

export interface WeeklyDataPoint {
  day: string;      // e.g. "Sen", "Sel", etc.
  fullDate: string;  // e.g. "2026-05-12"
  total: number;
}

interface Props {
  data: WeeklyDataPoint[];
}

export default function WeeklyTrendChart({ data }: Props) {
  return (
    <div className="analytics-card">
      <div className="analytics-card__header">
        <span className="analytics-card__dot analytics-card__dot--blue" />
        Trend Mingguan
      </div>
      <div className="analytics-card__body">
        <ResponsiveContainer width="100%" height={260}>
          <AreaChart data={data} margin={{ top: 8, right: 8, left: -12, bottom: 0 }}>
            <defs>
              <linearGradient id="trendGrad" x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%" stopColor="#2563EB" stopOpacity={0.25} />
                <stop offset="95%" stopColor="#2563EB" stopOpacity={0.02} />
              </linearGradient>
            </defs>
            <CartesianGrid strokeDasharray="3 3" stroke="#E5E7EB" vertical={false} />
            <XAxis
              dataKey="day"
              tick={{ fontSize: 11, fill: '#6B7280' }}
              axisLine={{ stroke: '#E5E7EB' }}
              tickLine={false}
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
              labelFormatter={(_: string, payload) => {
                if (payload?.[0]?.payload?.fullDate) return payload[0].payload.fullDate;
                return _;
              }}
              formatter={(value: number) => [value, 'Deteksi']}
            />
            <Area
              type="monotone"
              dataKey="total"
              stroke="#2563EB"
              strokeWidth={2.5}
              fill="url(#trendGrad)"
              dot={{ r: 4, fill: '#2563EB', stroke: '#fff', strokeWidth: 2 }}
              activeDot={{ r: 6, fill: '#2563EB', stroke: '#fff', strokeWidth: 2 }}
            />
          </AreaChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
