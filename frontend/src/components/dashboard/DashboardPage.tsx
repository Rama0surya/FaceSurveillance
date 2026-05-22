/**
 * DashboardPage — 3-column layout orchestrating all dashboard panels.
 *
 *   Left (250px):   StatsPanel (Today counter, Traffic chart, Comparison)
 *   Center (flex):  LiveVideoPanel + SnapshotStrip
 *   Right (280px):  RightPanel (Gender, Emotion, Age, Crowd)
 *
 * All child components are wrapped with React.memo() to prevent
 * cross-component re-render cascading.  For example, when a new
 * snapshot arrives and SnapshotStrip re-renders, LiveVideoPanel
 * does NOT re-render — the video stream stays uninterrupted.
 */

import { memo } from 'react';
import StatsPanel from './StatsPanel';
import LiveVideoPanel from './LiveVideoPanel';
import SnapshotStrip from './SnapshotStrip';
import TrafficMiniChart from './TrafficMiniChart';
import RightPanel from './RightPanel';

// Memoize siblings so that a store update in one panel
// doesn't trigger re-render of all other panels.
const MemoStatsPanel = memo(StatsPanel);
const MemoTrafficMiniChart = memo(TrafficMiniChart);
const MemoSnapshotStrip = memo(SnapshotStrip);
const MemoRightPanel = memo(RightPanel);

// LiveVideoPanel is already exported as memo() — no need to re-wrap.

export default function DashboardPage() {
  return (
    <div className="dashboard" id="dashboard-page">
      {/* Left column — Stats + Traffic */}
      <div className="stats-panel">
        <MemoStatsPanel />
        <MemoTrafficMiniChart />
      </div>

      {/* Center column — Video + Snapshots */}
      <div className="dashboard__center">
        <LiveVideoPanel />
        <MemoSnapshotStrip />
      </div>

      {/* Right column — Gender, Emotion, Age, Crowd */}
      <MemoRightPanel />
    </div>
  );
}
