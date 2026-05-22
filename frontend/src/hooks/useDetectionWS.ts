/**
 * EventSource (SSE) hook — connects to /api/stream/events/{camera_id} for live detection and snapshot events.
 *
 * Features:
 *   - Automatic native browser reconnection
 *   - Updates Zustand store: currentFaces, todayStats, snapshots, alerts, pipelineToggles
 *   - Handles event types: "connected", "detection", "snapshot", "toggle_changed"
 *   - Cleans up on camera switch or component unmount
 */

import { useEffect, useRef, useCallback } from 'react';
import { useCameraStore } from '@/store/cameraStore';
import type { Snapshot, Alert } from '@/store/cameraStore';

const API_BASE = import.meta.env.VITE_API_URL ?? 'http://localhost:8000';

export function useDetectionWS() {
  const activeCamera = useCameraStore((s) => s.activeCamera);
  const setCurrentFaces = useCameraStore((s) => s.setCurrentFaces);
  const setCurrentFrame = useCameraStore((s) => s.setCurrentFrame);
  const updateStats = useCameraStore((s) => s.updateStats);
  const addSnapshot = useCameraStore((s) => s.addSnapshot);
  const addAlert = useCameraStore((s) => s.addAlert);
  const setIsLive = useCameraStore((s) => s.setIsLive);
  const setPipelineToggles = useCameraStore((s) => s.setPipelineToggles);

  const esRef = useRef<EventSource | null>(null);

  const cleanup = useCallback(() => {
    if (esRef.current) {
      esRef.current.close();
      esRef.current = null;
    }
    setIsLive(false);
    setCurrentFaces([]);
    setCurrentFrame(null);
  }, [setIsLive, setCurrentFaces, setCurrentFrame]);

  const connect = useCallback(
    (cameraId: string, cameraName: string) => {
      cleanup();

      const url = `${API_BASE}/api/stream/events/${cameraId}`;
      const es = new EventSource(url);
      esRef.current = es;

      es.onopen = () => {
        setIsLive(true);
      };

      es.onmessage = (event) => {
        try {
          const msg = JSON.parse(event.data);

          switch (msg.type) {
            case 'connected': {
              setIsLive(true);
              break;
            }

            /* ---- Detection event ---- */
            case 'detection': {
              const data = msg.data;
              if (data) {
                // Update bounding boxes
                setCurrentFaces(data.faces ?? []);

                // Accumulate stats
                if (data.stats_delta) {
                  updateStats(data.stats_delta);
                }
              }
              break;
            }

            /* ---- Snapshot event ---- */
            case 'snapshot': {
              const snap = msg.data;
              if (snap) {
                const normalizedSnap: Snapshot = {
                  id: snap.id,
                  camera_id: snap.camera_id,
                  detection_id: snap.detection_id,
                  url: snap.url,
                  gender: snap.gender,
                  emotion: snap.emotion,
                  age: snap.age,
                  age_group: snap.age_group,
                  camera_name: cameraName,
                  timestamp: snap.timestamp ?? msg.timestamp,
                };
                addSnapshot(normalizedSnap);

                // Auto-generate alerts for angry / fear
                if (snap.emotion === 'angry' || snap.emotion === 'fear') {
                  const alert: Alert = {
                    id: `alert-${Date.now()}-${snap.id}`,
                    emotion: snap.emotion,
                    camera_name: cameraName,
                    timestamp: snap.timestamp ?? msg.timestamp,
                    snapshot_url: snap.url,
                  };
                  addAlert(alert);
                }
              }
              break;
            }

            /* ---- Global pipeline toggle update ---- */
            case 'toggle_changed': {
              if (msg.data) {
                setPipelineToggles(msg.data);
              }
              break;
            }

            default:
              break;
          }
        } catch {
          // ignore malformed messages
        }
      };

      es.onerror = () => {
        // EventSource will automatically attempt to reconnect,
        // but we flag that connection is currently lost.
        setIsLive(false);
      };
    },
    [
      cleanup,
      setIsLive,
      setCurrentFaces,
      updateStats,
      addSnapshot,
      addAlert,
      setPipelineToggles,
    ],
  );

  useEffect(() => {
    if (activeCamera) {
      connect(activeCamera.id, activeCamera.name);
    } else {
      cleanup();
    }
    return cleanup;
  }, [activeCamera?.id]); // eslint-disable-line react-hooks/exhaustive-deps
}
