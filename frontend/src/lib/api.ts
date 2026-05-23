/**
 * API helper — centralised fetch wrapper for the Face Surveillance backend.
 */

const API_BASE = import.meta.env.VITE_API_URL ?? 'http://localhost:8000';

/**
 * Generic JSON-GET helper with error handling.
 */
async function fetchJSON<T>(path: string): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`);
  if (!res.ok) {
    throw new Error(`API ${res.status}: ${res.statusText}`);
  }
  return res.json();
}

/**
 * Generic JSON-body helper (POST / PUT / DELETE).
 */
async function mutateJSON<T>(
  path: string,
  method: 'POST' | 'PUT' | 'DELETE',
  body?: unknown,
): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    method,
    headers: { 'Content-Type': 'application/json' },
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
  if (!res.ok) {
    throw new Error(`API ${res.status}: ${res.statusText}`);
  }
  // DELETE may return 204
  if (res.status === 204) return undefined as unknown as T;
  return res.json();
}

/* ------------------------------------------------------------------ */
/* Stats                                                               */
/* ------------------------------------------------------------------ */

export interface TodayStatsResponse {
  total: number;
  male: number;
  female: number;
  emotions: Record<string, number>;
  ages: Record<string, number>;
}

export async function fetchTodayStats(cameraId: string) {
  return fetchJSON<TodayStatsResponse>(`/api/stats/today?camera_id=${cameraId}`);
}

export interface HourlyRow {
  hour: number;
  total: number;
  male: number;
  female: number;
}

export async function fetchHourlyStats(cameraId: string, date?: string) {
  const params = new URLSearchParams({ camera_id: cameraId });
  if (date) params.set('date', date);
  return fetchJSON<{ data: HourlyRow[] }>(`/api/stats/hourly?${params}`);
}

export interface ComparisonResponse {
  today: { total: number };
  yesterday: { total: number };
  change_pct: number;
}

export async function fetchComparisonStats(cameraId: string) {
  return fetchJSON<ComparisonResponse>(`/api/stats/comparison?camera_id=${cameraId}`);
}

/* ------------------------------------------------------------------ */
/* Snapshots                                                           */
/* ------------------------------------------------------------------ */

export interface SnapshotRow {
  id: string;
  camera_id: string;
  detection_id: string;
  url: string;
  gender: string;
  emotion: string;
  age: number;
  age_group: string;
  camera_name: string;
  timestamp: string;
}

export async function fetchSnapshots(opts: {
  cameraId?: string;
  date?: string;
  emotion?: string;
  gender?: string;
  age_group?: string;
  limit?: number;
  offset?: number;
}) {
  const params = new URLSearchParams();
  if (opts.cameraId) params.set('camera_id', opts.cameraId);
  if (opts.date) params.set('date', opts.date);
  if (opts.emotion) params.set('emotion', opts.emotion);
  if (opts.gender) params.set('gender', opts.gender);
  if (opts.age_group) params.set('age_group', opts.age_group);
  if (opts.limit) params.set('limit', String(opts.limit));
  if (opts.offset) params.set('offset', String(opts.offset));
  return fetchJSON<{ data: SnapshotRow[]; count: number }>(`/api/snapshots?${params}`);
}

/* ------------------------------------------------------------------ */
/* Cameras                                                             */
/* ------------------------------------------------------------------ */

export async function fetchCameras() {
  return fetchJSON<Array<{ id: string; name: string; rtsp_url: string; status: string }>>('/api/cameras');
}

/* ------------------------------------------------------------------ */
/* Alert Rules                                                         */
/* ------------------------------------------------------------------ */

import type { AlertRule, AlertFull } from '@/store/cameraStore';

export async function fetchAlertRules() {
  return fetchJSON<AlertRule[]>('/api/alerts/rules');
}

export async function createAlertRule(data: Omit<AlertRule, 'id' | 'created_at'>) {
  return mutateJSON<AlertRule>('/api/alerts/rules', 'POST', data);
}

export async function updateAlertRule(id: string, data: Partial<AlertRule>) {
  return mutateJSON<AlertRule>(`/api/alerts/rules/${id}`, 'PUT', data);
}

export async function deleteAlertRule(id: string) {
  return mutateJSON<void>(`/api/alerts/rules/${id}`, 'DELETE');
}

/* ------------------------------------------------------------------ */
/* Alerts                                                              */
/* ------------------------------------------------------------------ */

export async function fetchAlerts(params?: {
  camera_id?: string;
  severity?: string;
  is_read?: boolean;
  limit?: number;
  offset?: number;
}) {
  const qs = new URLSearchParams();
  if (params?.camera_id) qs.set('camera_id', params.camera_id);
  if (params?.severity) qs.set('severity', params.severity);
  if (params?.is_read !== undefined) qs.set('is_read', String(params.is_read));
  if (params?.limit) qs.set('limit', String(params.limit));
  if (params?.offset) qs.set('offset', String(params.offset));
  return fetchJSON<{ data: AlertFull[]; count: number }>(`/api/alerts?${qs}`);
}

export async function fetchUnreadCount() {
  return fetchJSON<{ count: number }>('/api/alerts/unread-count');
}

export async function markAlertRead(id: string) {
  return mutateJSON<AlertFull>(`/api/alerts/${id}/read`, 'PUT');
}

export async function markAllAlertsRead() {
  return mutateJSON<{ updated: number }>('/api/alerts/mark-all-read', 'POST');
}

export async function resolveAlert(id: string, resolved_by?: string) {
  return mutateJSON<AlertFull>(`/api/alerts/${id}/resolve`, 'PUT', { resolved_by });
}

/* ------------------------------------------------------------------ */
/* Settings                                                            */
/* ------------------------------------------------------------------ */

export async function fetchSystemInfo() {
  return fetchJSON<Record<string, any>>('/api/settings/system-info');
}

export async function fetchHardwareInfo() {
  return fetchJSON<{ gpu: Record<string, any>; cpu: Record<string, any> }>('/api/settings/hardware');
}

export async function fetchModelInfo() {
  return fetchJSON<Record<string, any>>('/api/settings/models');
}

/* ---- Pipeline Toggles ---- */

export interface PipelineToggles {
  tracking_enabled: boolean;
  insightface_enabled: boolean;
}

export async function fetchPipelineToggles() {
  return fetchJSON<PipelineToggles>('/api/settings/pipeline-toggles');
}

export async function updatePipelineToggles(data: Partial<PipelineToggles>) {
  return mutateJSON<PipelineToggles>('/api/settings/pipeline-toggles', 'PUT', data);
}

/* ---- Detection Config ---- */

export interface DetectionConfigPayload {
  detection_interval?: number;
  frame_fps?: number;
  deepface_model?: string;
  face_detector?: string;
  capture_min_confidence?: number;
  min_face_size?: number;
  capture_cooldown?: number;
}

export interface DetectionConfigResponse {
  detection_interval: number;
  frame_fps: number;
  deepface_model: string;
  face_detector: string;
  yolo_confidence: number;
  face_tracker: string;
  track_reanalyze_ttl: number;
  capture_min_confidence: number;
  min_face_size: number;
  capture_cooldown: number;
}

export async function updateDetectionConfig(data: DetectionConfigPayload) {
  return mutateJSON<DetectionConfigResponse>('/api/settings/detection-config', 'PUT', data);
}

export async function fetchHealthCheck() {
  return fetchJSON<{
    api_status: string;
    supabase_connected: boolean;
    active_streams: number;
    uptime_seconds: number;
    version: string;
  }>('/api/settings/health');
}

/* ------------------------------------------------------------------ */
/* AI Search                                                          */
/* ------------------------------------------------------------------ */

export interface SearchSnapshotRow extends SnapshotRow {
  similarity: number;
}

export async function searchSnapshotsByText(opts: {
  query: string;
  cameraId?: string;
  limit?: number;
  similarityThreshold?: number;
}) {
  const res = await fetch(`${API_BASE}/api/search/text`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      query: opts.query,
      camera_id: opts.cameraId || undefined,
      limit: opts.limit ?? 20,
      similarity_threshold: opts.similarityThreshold ?? 0.15,
    }),
  });
  if (!res.ok) {
    throw new Error(`Text search failed ${res.status}: ${res.statusText}`);
  }
  return res.json() as Promise<{ data: SearchSnapshotRow[]; count: number }>;
}

export async function searchSnapshotsByImage(opts: {
  file: File;
  cameraId?: string;
  limit?: number;
  similarityThreshold?: number;
}) {
  const formData = new FormData();
  formData.append('file', opts.file);
  if (opts.cameraId) formData.append('camera_id', opts.cameraId);
  if (opts.limit) formData.append('limit', String(opts.limit));
  if (opts.similarityThreshold) {
    formData.append('similarity_threshold', String(opts.similarityThreshold));
  }

  const res = await fetch(`${API_BASE}/api/search/image`, {
    method: 'POST',
    body: formData,
  });
  if (!res.ok) {
    throw new Error(`Image search failed ${res.status}: ${res.statusText}`);
  }
  return res.json() as Promise<{ data: SearchSnapshotRow[]; count: number }>;
}

