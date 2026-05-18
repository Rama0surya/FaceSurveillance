/**
 * AgeDonutChart — Donut/Pie chart for 4 age groups:
 * Anak, Remaja, Dewasa, Lansia.
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
  ages: {
    child: number;
    teen: number;
    adult: number;
    elderly: number;
  };
}

const AGE_COLORS = ['#f59e0b', '#3b82f6', '#22c55e', '#8b5cf6'];

export default function AgeDonutChart({ ages }: Props) {
  const data = [
    { name: 'Anak', value: ages.child },
    { name: 'Remaja', value: ages.teen },
    { name: 'Dewasa', value: ages.adult },
    { name: 'Lansia', value: ages.elderly },
  ];

  const total = data.reduce((s, d) => s + d.value, 0);

  return (
    <div className="analytics-card">
      <div className="analytics-card__header">
        <span className="analytics-card__dot analytics-card__dot--purple" />
        Distribusi Kelompok Usia
      </div>
      <div className="analytics-card__body analytics-card__body--center">
        <ResponsiveContainer width="100%" height={260}>
          <PieChart>
            <Pie
              data={data}
              cx="50%"
              cy="50%"
              innerRadius={55}
              outerRadius={90}
              dataKey="value"
              stroke="#fff"
              strokeWidth={3}
              paddingAngle={2}
            >
              {data.map((_, i) => (
                <Cell key={i} fill={AGE_COLORS[i]} />
              ))}
            </Pie>
            {/* Center label */}
            <text
              x="50%"
              y="48%"
              textAnchor="middle"
              dominantBaseline="central"
              fontSize={28}
              fontWeight={700}
              fill="#111827"
            >
              {total}
            </text>
            <text
              x="50%"
              y="58%"
              textAnchor="middle"
              dominantBaseline="central"
              fontSize={11}
              fill="#6B7280"
            >
              Total
            </text>
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
