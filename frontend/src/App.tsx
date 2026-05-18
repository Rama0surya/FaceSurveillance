/**
 * App — root component. Mounts AppShell and conditionally renders
 * the active page (Dashboard or Camera Config) based on Zustand state.
 *
 * On mount: fetches cameras, today stats, hourly data, and comparison traffic.
 * Re-fetches stats whenever the active camera changes.
 */

import { useEffect, useCallback } from 'react';
import AppShell from '@/components/layout/AppShell';
import DashboardPage from '@/components/dashboard/DashboardPage';
import CameraConfigPage from '@/components/cameras/CameraConfigPage';
import AnalyticsPage from '@/components/analytics/AnalyticsPage';
import SnapshotGalleryPage from '@/components/snapshots/SnapshotGalleryPage';
import AlertsPage from '@/components/alerts/AlertsPage';
import SettingsPage from '@/components/settings/SettingsPage';
import AlertToast from '@/components/alerts/AlertToast';
import { useDetectionWS } from '@/hooks/useDetectionWS';
import { useCameraStore } from '@/store/cameraStore';
import type { Camera, TodayStats } from '@/store/cameraStore';
import {
  fetchTodayStats,
  fetchHourlyStats,
  fetchComparisonStats,
} from '@/lib/api';

const API_BASE = import.meta.env.VITE_API_URL ?? 'http://localhost:8000';

function App() {
  const setCameras = useCameraStore((s) => s.setCameras);
  const setActiveCamera = useCameraStore((s) => s.setActiveCamera);
  const activePage = useCameraStore((s) => s.activePage);
  const activeCamera = useCameraStore((s) => s.activeCamera);
  const setTodayStats = useCameraStore((s) => s.setTodayStats);
  const setHourlyData = useCameraStore((s) => s.setHourlyData);
  const setComparisonData = useCameraStore((s) => s.setComparisonData);

  // Connect the WebSocket hook
  useDetectionWS();

  // Fetch cameras on mount
  useEffect(() => {
    fetchCameras();
  }, []);

  async function fetchCameras() {
    try {
      const res = await fetch(`${API_BASE}/api/cameras`);
      if (res.ok) {
        const data: Camera[] = await res.json();
        setCameras(data);
        // Auto-select first camera if none selected
        if (data.length > 0) {
          setActiveCamera(data[0]);
        }
      }
    } catch {
      // Backend may not be running — use mock cameras for development
      const mockCameras: Camera[] = [
        {
          id: 'cam-001',
          name: 'Lobby Utama',
          rtsp_url: 'rtsp://192.168.1.10:554/stream1',
          status: 'live',
        },
        {
          id: 'cam-002',
          name: 'Pintu Masuk',
          rtsp_url: 'rtsp://192.168.1.11:554/stream1',
          status: 'offline',
        },
        {
          id: 'cam-003',
          name: 'Area Parkir',
          rtsp_url: 'rtsp://192.168.1.12:554/stream1',
          status: 'processing',
        },
      ];
      setCameras(mockCameras);
      setActiveCamera(mockCameras[0]);
    }
  }

  /**
   * Fetch all dashboard stats whenever the active camera changes.
   */
  const fetchDashboardData = useCallback(
    async (cameraId: string) => {
      const today = new Date().toISOString().slice(0, 10); // YYYY-MM-DD

      // Fetch today stats
      try {
        const stats = await fetchTodayStats(cameraId);
        const normalized: TodayStats = {
          total: stats.total ?? 0,
          male: stats.male ?? 0,
          female: stats.female ?? 0,
          emotions: {
            happy: stats.emotions?.happy ?? 0,
            sad: stats.emotions?.sad ?? 0,
            angry: stats.emotions?.angry ?? 0,
            neutral: stats.emotions?.neutral ?? 0,
            fear: stats.emotions?.fear ?? 0,
          },
          ages: {
            child: stats.ages?.child ?? 0,
            teen: stats.ages?.teen ?? 0,
            adult: stats.ages?.adult ?? 0,
            elderly: stats.ages?.elderly ?? 0,
          },
        };
        setTodayStats(normalized);
      } catch {
        // silently fail — websocket will keep stats updated
      }

      // Fetch hourly data
      try {
        const hourly = await fetchHourlyStats(cameraId, today);
        if (hourly.data) {
          setHourlyData(hourly.data);
        }
      } catch {
        // silently fail
      }

      // Fetch comparison stats
      try {
        const comparison = await fetchComparisonStats(cameraId);
        setComparisonData(comparison);
      } catch {
        // silently fail
      }
    },
    [setTodayStats, setHourlyData, setComparisonData],
  );

  // Trigger stat-fetch on camera change
  useEffect(() => {
    if (activeCamera?.id) {
      fetchDashboardData(activeCamera.id);
    }
  }, [activeCamera?.id, fetchDashboardData]);

  /** Render the active page based on sidebar selection */
  function renderPage() {
    switch (activePage) {
      case 'cameras':
        return <CameraConfigPage />;
      case 'analytics':
        return <AnalyticsPage />;
      case 'snapshots':
        return <SnapshotGalleryPage />;
      case 'alerts':
        return <AlertsPage />;
      case 'settings':
        return <SettingsPage />;
      case 'dashboard':
      default:
        return <DashboardPage />;
    }
  }

  return (
    <>
      <AppShell>
        {renderPage()}
      </AppShell>
      <AlertToast />
    </>
  );
}

export default App;

