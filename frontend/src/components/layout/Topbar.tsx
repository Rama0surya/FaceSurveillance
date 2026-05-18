/**
 * Topbar — camera title, LIVE badge, camera selector, and real-time clock.
 */

import { useEffect, useState } from 'react';
import { Radio, ChevronDown, Clock } from 'lucide-react';
import { useCameraStore } from '@/store/cameraStore';

export default function Topbar() {
  const cameras = useCameraStore((s) => s.cameras);
  const activeCamera = useCameraStore((s) => s.activeCamera);
  const isLive = useCameraStore((s) => s.isLive);
  const setActiveCamera = useCameraStore((s) => s.setActiveCamera);

  const [clock, setClock] = useState(formatTime());

  useEffect(() => {
    const interval = setInterval(() => setClock(formatTime()), 1000);
    return () => clearInterval(interval);
  }, []);

  function handleCameraChange(e: React.ChangeEvent<HTMLSelectElement>) {
    const cam = cameras.find((c) => c.id === e.target.value) ?? null;
    setActiveCamera(cam);
  }

  return (
    <header className="topbar">
      {/* Left: Camera name + LIVE badge */}
      <div className="topbar__left">
        <h1 className="topbar__title">
          {activeCamera?.name ?? 'No Camera Selected'}
        </h1>
        {isLive && (
          <span className="topbar__live-badge" id="live-badge">
            <Radio size={12} />
            LIVE
          </span>
        )}
        {!isLive && activeCamera && (
          <span className="topbar__offline-badge">OFFLINE</span>
        )}
      </div>

      {/* Right: Camera selector + Clock */}
      <div className="topbar__right">
        {/* Camera selector */}
        <div className="topbar__selector-wrapper">
          <select
            id="camera-selector"
            className="topbar__selector"
            value={activeCamera?.id ?? ''}
            onChange={handleCameraChange}
          >
            <option value="">Select Camera</option>
            {cameras.map((cam) => (
              <option key={cam.id} value={cam.id}>
                {cam.name}
              </option>
            ))}
          </select>
          <ChevronDown size={14} className="topbar__selector-chevron" />
        </div>

        {/* Clock */}
        <div className="topbar__clock" id="live-clock">
          <Clock size={14} />
          <span>{clock}</span>
        </div>
      </div>
    </header>
  );
}

function formatTime(): string {
  return new Date().toLocaleTimeString('en-GB', {
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  });
}
