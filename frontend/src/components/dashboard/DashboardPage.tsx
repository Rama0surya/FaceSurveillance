/**
 * DashboardPage — 3-column layout orchestrating all dashboard panels.
 *
 *   Left (250px):   StatsPanel (Today counter, Traffic chart, Comparison)
 *   Center (flex):  LiveVideoPanel + SnapshotStrip
 *   Right (280px):  RightPanel (Gender, Emotion, Age, Crowd)
 */

import StatsPanel from './StatsPanel';
import LiveVideoPanel from './LiveVideoPanel';
import SnapshotStrip from './SnapshotStrip';
import TrafficMiniChart from './TrafficMiniChart';
import RightPanel from './RightPanel';

export default function DashboardPage() {
  return (
    <div className="dashboard" id="dashboard-page">
      {/* Left column — Stats + Traffic */}
      <div className="stats-panel">
        <StatsPanel />
        <TrafficMiniChart />
      </div>

      {/* Center column — Video + Snapshots */}
      <div className="dashboard__center">
        <LiveVideoPanel />
        <SnapshotStrip />
      </div>

      {/* Right column — Gender, Emotion, Age, Crowd */}
      <RightPanel />
    </div>
  );
}
