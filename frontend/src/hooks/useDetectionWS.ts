/**
 * WebSocket hook — connects to /ws/stream/{camera_id} for live detection data.
 *
 * Features:
 *   - Auto-reconnect with exponential backoff (1s → 30s max)
 *   - Updates Zustand store: currentFaces, todayStats, snapshots, alerts
 *   - Handles message types: "frame", "detection", "stats"
 *   - Cleans up on camera switch or component unmount
 */

import { useEffect, useRef, useCallback } from 'react';
import { useCameraStore } from '@/store/cameraStore';
import type { Snapshot, Alert, TodayStats } from '@/store/cameraStore';

const WS_BASE = import.meta.env.VITE_WS_URL ?? 'ws://localhost:8000';
const MAX_RECONNECT_DELAY = 30_000;

export function useDetectionWS() {
  const activeCamera = useCameraStore((s) => s.activeCamera);
  const setCurrentFaces = useCameraStore((s) => s.setCurrentFaces);
  const setCurrentFrame = useCameraStore((s) => s.setCurrentFrame);
  const updateStats = useCameraStore((s) => s.updateStats);
  const setTodayStats = useCameraStore((s) => s.setTodayStats);
  const addSnapshot = useCameraStore((s) => s.addSnapshot);
  const addAlert = useCameraStore((s) => s.addAlert);
  const setIsLive = useCameraStore((s) => s.setIsLive);
  const setWsConnection = useCameraStore((s) => s.setWsConnection);

  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const reconnectDelay = useRef(1000);
  const shouldReconnect = useRef(true);

  const cleanup = useCallback(() => {
    shouldReconnect.current = false;
    if (reconnectTimer.current) {
      clearTimeout(reconnectTimer.current);
      reconnectTimer.current = null;
    }
    if (wsRef.current) {
      wsRef.current.close();
      wsRef.current = null;
    }
    setIsLive(false);
    setWsConnection(null);
    setCurrentFaces([]);
    setCurrentFrame(null);
  }, [setIsLive, setWsConnection, setCurrentFaces, setCurrentFrame]);

  const connect = useCallback(
    (cameraId: string, cameraName: string) => {
      cleanup();
      shouldReconnect.current = true;
      reconnectDelay.current = 1000;

      const url = `${WS_BASE}/ws/stream/${cameraId}`;
      const ws = new WebSocket(url);
      wsRef.current = ws;

      ws.onopen = () => {
        setIsLive(true);
        setWsConnection(ws);
        reconnectDelay.current = 1000; // reset on success
      };

      ws.onmessage = (event) => {
        try {
          const msg = JSON.parse(event.data);

          switch (msg.type) {
            /* ---- Frame update ---- */
            case 'frame': {
              if (msg.data) {
                setCurrentFrame(msg.data);
              }
              break;
            }

            /* ---- Detection event ---- */
            case 'detection': {
              // Update bounding boxes
              setCurrentFaces(msg.faces ?? []);

              // Update frame if provided
              if (msg.frame) {
                setCurrentFrame(msg.frame);
              }

              // Accumulate stats
              if (msg.stats_delta) {
                updateStats(msg.stats_delta);
              }

              // Add snapshots from detected faces
              if (msg.faces && msg.faces.length > 0) {
                for (const face of msg.faces) {
                  if (face.snapshot_url) {
                    const snap: Snapshot = {
                      id: face.id,
                      camera_id: cameraId,
                      detection_id: msg.detection_id ?? face.id,
                      url: face.snapshot_url,
                      gender: face.gender,
                      emotion: face.emotion,
                      age: face.age,
                      age_group: face.age_group,
                      camera_name: cameraName,
                      timestamp: msg.timestamp,
                    };
                    addSnapshot(snap);

                    // Auto-generate alerts for angry / fear
                    if (face.emotion === 'angry' || face.emotion === 'fear') {
                      const alert: Alert = {
                        id: `alert-${Date.now()}-${face.id}`,
                        emotion: face.emotion,
                        camera_name: cameraName,
                        timestamp: msg.timestamp,
                        snapshot_url: face.snapshot_url,
                      };
                      addAlert(alert);
                    }
                  }
                }
              }
              break;
            }

            /* ---- Stats push ---- */
            case 'stats': {
              // Full stats replacement from server broadcast
              if (msg.data) {
                const s = msg.data;
                const normalized: TodayStats = {
                  total: s.total ?? 0,
                  male: s.male ?? 0,
                  female: s.female ?? 0,
                  emotions: {
                    happy: s.emotions?.happy ?? 0,
                    sad: s.emotions?.sad ?? 0,
                    angry: s.emotions?.angry ?? 0,
                    neutral: s.emotions?.neutral ?? 0,
                    fear: s.emotions?.fear ?? 0,
                  },
                  ages: {
                    child: s.ages?.child ?? 0,
                    teen: s.ages?.teen ?? 0,
                    adult: s.ages?.adult ?? 0,
                    elderly: s.ages?.elderly ?? 0,
                  },
                };
                setTodayStats(normalized);
              }
              break;
            }

            /* ---- Backend-pushed alert ---- */
            case 'alert': {
              if (msg.data) {
                const a = msg.data;
                const alert: Alert = {
                  id: a.id ?? `alert-${Date.now()}`,
                  emotion: a.alert_type ?? a.metadata?.emotion ?? 'unknown',
                  camera_name: a.camera_name ?? cameraName,
                  timestamp: a.created_at ?? new Date().toISOString(),
                  snapshot_url: a.metadata?.snapshot_url ?? '',
                };
                addAlert(alert);
              }
              break;
            }

            default:
              // Legacy format: no type field — treat as detection
              if (msg.faces) {
                setCurrentFaces(msg.faces);
                if (msg.frame) setCurrentFrame(msg.frame);
                if (msg.stats_delta) updateStats(msg.stats_delta);
              }
              break;
          }
        } catch {
          // ignore malformed messages
        }
      };

      ws.onclose = () => {
        setIsLive(false);
        setWsConnection(null);

        if (shouldReconnect.current) {
          reconnectTimer.current = setTimeout(() => {
            connect(cameraId, cameraName);
          }, reconnectDelay.current);
          reconnectDelay.current = Math.min(
            reconnectDelay.current * 2,
            MAX_RECONNECT_DELAY,
          );
        }
      };

      ws.onerror = () => {
        ws.close();
      };
    },
    [
      cleanup,
      setIsLive,
      setWsConnection,
      setCurrentFaces,
      setCurrentFrame,
      updateStats,
      setTodayStats,
      addSnapshot,
      addAlert,
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
