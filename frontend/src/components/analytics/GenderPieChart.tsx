/**
 * GenderPieChart — Pie chart comparing Male (blue) vs Female (pink).
 * Shows percentage labels.
 */

import {
  PieChart,
  Pie,
  Cell,
  Tooltip,
  ResponsiveContainer,
  Legend,
} from 'recharts';

interface Props {
  male: number;
  female: number;
}

const COLORS = ['#2563EB', '#EC4899'];

const RADIAN = Math.PI / 180;

function renderLabel({
  cx,
  cy,
  midAngle,
  innerRadius,
  outerRadius,
  percent,
}: // eslint-disable-next-line @typescript-eslint/no-explicit-any
any) {
  const radius = innerRadius + (outerRadius - innerRadius) * 0.5;
  const x = cx + radius * Math.cos(-midAngle * RADIAN);
  const y = cy + radius * Math.sin(-midAngle * RADIAN);
  if (percent === 0) return null;
  return (
    <text
      x={x}
      y={y}
      fill="#fff"
      textAnchor="middle"
      dominantBaseline="central"
      fontSize={13}
      fontWeight={700}
    >
      {`${(percent * 100).toFixed(1)}%`}
    </text>
  );
}

export default function GenderPieChart({ male, female }: Props) {
  const data = [
    { name: 'Pria', value: male },
    { name: 'Wanita', value: female },
  ];

  return (
    <div className="analytics-card">
      <div className="analytics-card__header">
        <span className="analytics-card__dot analytics-card__dot--pink" />
        Perbandingan Gender
      </div>
      <div className="analytics-card__body analytics-card__body--center">
        <ResponsiveContainer width="100%" height={260}>
          <PieChart>
            <Pie
              data={data}
              cx="50%"
              cy="50%"
              outerRadius={95}
              dataKey="value"
              labelLine={false}
              label={renderLabel}
              stroke="#fff"
              strokeWidth={3}
            >
              {data.map((_, i) => (
                <Cell key={i} fill={COLORS[i]} />
              ))}
            </Pie>
            <Tooltip
              contentStyle={{
                background: '#fff',
                border: '1px solid #E5E7EB',
                borderRadius: 8,
                fontSize: 12,
                boxShadow: '0 4px 12px rgba(0,0,0,0.08)',
              }}
              formatter={(value: number) => [value, 'Orang']}
            />
            <Legend
              verticalAlign="bottom"
              iconType="circle"
              iconSize={10}
              formatter={(value: string) => (
                <span style={{ fontSize: 12, color: '#374151', fontWeight: 500 }}>
                  {value}
                </span>
              )}
            />
          </PieChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
