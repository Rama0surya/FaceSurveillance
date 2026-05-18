/**
 * TrafficMiniChart — hourly detection traffic chart using Recharts AreaChart.
 * Light theme styling with blue accent.
 */

import { useCameraStore } from '@/store/cameraStore';
import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  CartesianGrid,
} from 'recharts';
import { TrendingUp } from 'lucide-react';

export default function TrafficMiniChart() {
  const hourlyData = useCameraStore((s) => s.hourlyData);

  const data =
    hourlyData.length > 0 ? hourlyData : defaultHourly();

  return (
    <div className="traffic-chart" id="traffic-mini-chart">
      <div className="traffic-chart__header">
        <TrendingUp size={14} />
        <span>Comparison Traffic</span>
      </div>
      <div className="traffic-chart__body">
        <ResponsiveContainer width="100%" height={120}>
          <AreaChart data={data} margin={{ top: 4, right: 4, bottom: 0, left: -20 }}>
            <defs>
              <linearGradient id="trafficGrad" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor="#2563EB" stopOpacity={0.2} />
                <stop offset="100%" stopColor="#2563EB" stopOpacity={0.02} />
              </linearGradient>
            </defs>
            <CartesianGrid
              strokeDasharray="3 3"
              stroke="#E5E7EB"
              vertical={false}
            />
            <XAxis
              dataKey="hour"
              tickFormatter={(h) => `${h}h`}
              tick={{ fontSize: 10, fill: '#9CA3AF' }}
              axisLine={false}
              tickLine={false}
              interval={3}
            />
            <YAxis
              tick={{ fontSize: 10, fill: '#9CA3AF' }}
              axisLine={false}
              tickLine={false}
              allowDecimals={false}
            />
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
              fill="url(#trafficGrad)"
              strokeWidth={2}
            />
          </AreaChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}

function defaultHourly() {
  return Array.from({ length: 24 }, (_, i) => ({ hour: i, total: 0 }));
}
