/**
 * Zustand store — central state for the Face Surveillance dashboard.
 */

import { create } from 'zustand';

/* ------------------------------------------------------------------ */
/* Types                                                               */
/* ------------------------------------------------------------------ */

export interface Camera {
  id: string;
  name: string;
  rtsp_url: string;
  status: 'offline' | 'live' | 'processing';
  created_at?: string;
}

export interface BBox {
  x: number;
  y: number;
  w: number;
  h: number;
}

export interface DetectionFace {
  id: string;
  bbox: BBox;
  gender: string;
  emotion: string;
  age_group: string;
  age: number;
  confidence: number;
  snapshot_url: string;
}

export interface Snapshot {
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

export interface TodayStats {
  total: number;
  male: number;
  female: number;
  emotions: {
    happy: number;
    sad: number;
    angry: number;
    neutral: number;
    fear: number;
  };
  ages: {
    child: number;
    teen: number;
    adult: number;
    elderly: number;
  };
}

export interface HourlyBucket {
  hour: number;
  total: number;
}

export interface Alert {
  id: string;
  emotion: string;
  camera_name: string;
  timestamp: string;
  snapshot_url: string;
}

export interface AlertRule {
  id: string;
  name: string;
  rule_type: 'emotion' | 'crowd_count' | 'unknown_face' | 'age_group';
  condition: Record<string, any>;
  severity: 'info' | 'warning' | 'critical';
  camera_id: string | null;
  is_active: boolean;
  cooldown_seconds: number;
  created_at?: string;
}

export interface AlertFull {
  id: string;
  rule_id: string | null;
  camera_id: string;
  alert_type: string;
  severity: 'info' | 'warning' | 'critical';
  message: string;
  metadata: Record<string, any> | null;
  is_read: boolean;
  is_resolved: boolean;
  created_at?: string;
}

export interface ComparisonData {
  today: { total: number };
  yesterday: { total: number };
  change_pct: number;
}

/** A point on the detection-zone canvas (normalized 0–1) */
export interface ZonePoint {
  x: number;
  y: number;
}

/** Active page enum */
export type ActivePage = 'dashboard' | 'cameras' | 'analytics' | 'snapshots' | 'alerts' | 'settings';

/** Pipeline toggle state (synced with backend) */
export interface PipelineToggles {
  tracking_enabled: boolean;
  insightface_enabled: boolean;
}

/* ------------------------------------------------------------------ */
/* Store                                                               */
/* ------------------------------------------------------------------ */

interface CameraStore {
  /* Data */
  cameras: Camera[];
  activeCamera: Camera | null;
  isLive: boolean;

  todayStats: TodayStats;
  currentFaces: DetectionFace[];
  snapshots: Snapshot[];
  hourlyData: HourlyBucket[];
  alerts: Alert[];
  alertRules: AlertRule[];
  alertHistory: AlertFull[];
  unreadAlertCount: number;
  currentFrame: string | null;
  comparisonData: ComparisonData | null;

  wsConnection: WebSocket | null;

  /** Currently active page in the sidebar */
  activePage: ActivePage;

  /** Detection-zone coordinates keyed by camera id */
  detectionZones: Record<string, ZonePoint[]>;

  /** Pipeline model toggles (tracking ON/OFF, analysis ON/OFF) */
  pipelineToggles: PipelineToggles;

  /* Actions */
  setCameras: (cameras: Camera[]) => void;
  setActiveCamera: (camera: Camera | null) => void;
  setIsLive: (live: boolean) => void;

  setCurrentFaces: (faces: DetectionFace[]) => void;
  setCurrentFrame: (frame: string | null) => void;

  setTodayStats: (stats: TodayStats) => void;
  updateStats: (delta: {
    total: number;
    male?: number;
    female?: number;
    emotion?: string;
    age_group?: string;
  }) => void;
  resetStats: () => void;

  addSnapshot: (snapshot: Snapshot) => void;
  setSnapshots: (snapshots: Snapshot[]) => void;
  setHourlyData: (data: HourlyBucket[]) => void;
  addAlert: (alert: Alert) => void;
  setAlertRules: (rules: AlertRule[]) => void;
  setAlertHistory: (alerts: AlertFull[]) => void;
  setUnreadAlertCount: (count: number) => void;
  markAlertAsRead: (alertId: string) => void;
  setComparisonData: (data: ComparisonData) => void;

  setWsConnection: (ws: WebSocket | null) => void;

  /* Navigation */
  setActivePage: (page: ActivePage) => void;

  /* Camera CRUD */
  addCamera: (camera: Camera) => void;
  updateCamera: (id: string, patch: Partial<Pick<Camera, 'name' | 'rtsp_url'>>) => void;
  removeCamera: (id: string) => void;
  updateCameraStatus: (id: string, status: Camera['status']) => void;

  /* Detection zones */
  setDetectionZone: (cameraId: string, points: ZonePoint[]) => void;
  clearDetectionZone: (cameraId: string) => void;

  /* Pipeline toggles */
  setPipelineToggles: (toggles: PipelineToggles) => void;
}

const initialStats: TodayStats = {
  total: 0,
  male: 0,
  female: 0,
  emotions: { happy: 0, sad: 0, angry: 0, neutral: 0, fear: 0 },
  ages: { child: 0, teen: 0, adult: 0, elderly: 0 },
};

export const useCameraStore = create<CameraStore>((set) => ({
  cameras: [],
  activeCamera: null,
  isLive: false,

  todayStats: { ...initialStats },
  currentFaces: [],
  snapshots: [],
  hourlyData: [],
  alerts: [],
  alertRules: [],
  alertHistory: [],
  unreadAlertCount: 0,
  currentFrame: null,
  comparisonData: null,

  wsConnection: null,

  activePage: 'dashboard',
  detectionZones: {},
  pipelineToggles: { tracking_enabled: true, insightface_enabled: true },

  /* ---- Actions ---- */

  setCameras: (cameras) => set({ cameras }),

  setActiveCamera: (camera) => set({ activeCamera: camera }),

  setIsLive: (live) => set({ isLive: live }),

  setCurrentFaces: (faces) => set({ currentFaces: faces }),

  setCurrentFrame: (frame) => set({ currentFrame: frame }),

  setTodayStats: (stats) => set({ todayStats: stats }),

  updateStats: (delta) =>
    set((state) => {
      const s = { ...state.todayStats };
      s.total += delta.total;
      s.male += delta.male ?? 0;
      s.female += delta.female ?? 0;

      if (delta.emotion && delta.emotion in s.emotions) {
        (s.emotions as Record<string, number>)[delta.emotion] += delta.total;
      }
      if (delta.age_group) {
        const ageMap: Record<string, keyof TodayStats['ages']> = {
          anak: 'child',
          remaja: 'teen',
          dewasa: 'adult',
          lansia: 'elderly',
        };
        const key = ageMap[delta.age_group];
        if (key) s.ages[key] += delta.total;
      }
      return { todayStats: s };
    }),

  resetStats: () => set({ todayStats: { ...initialStats } }),

  addSnapshot: (snapshot) =>
    set((state) => ({
      snapshots: [snapshot, ...state.snapshots].slice(0, 50),
    })),

  setSnapshots: (snapshots) => set({ snapshots }),

  setHourlyData: (data) => set({ hourlyData: data }),

  addAlert: (alert) =>
    set((state) => ({
      alerts: [alert, ...state.alerts].slice(0, 20),
      unreadAlertCount: state.unreadAlertCount + 1,
    })),

  setAlertRules: (rules) => set({ alertRules: rules }),

  setAlertHistory: (alerts) => set({ alertHistory: alerts }),

  setUnreadAlertCount: (count) => set({ unreadAlertCount: count }),

  markAlertAsRead: (alertId) =>
    set((state) => ({
      alertHistory: state.alertHistory.map((a) =>
        a.id === alertId ? { ...a, is_read: true } : a
      ),
      unreadAlertCount: Math.max(0, state.unreadAlertCount - 1),
    })),

  setComparisonData: (data) => set({ comparisonData: data }),

  setWsConnection: (ws) => set({ wsConnection: ws }),

  /* ---- Navigation ---- */

  setActivePage: (page) => set({ activePage: page }),

  /* ---- Camera CRUD ---- */

  addCamera: (camera) =>
    set((state) => ({ cameras: [...state.cameras, camera] })),

  updateCamera: (id, patch) =>
    set((state) => ({
      cameras: state.cameras.map((c) =>
        c.id === id ? { ...c, ...patch } : c
      ),
    })),

  removeCamera: (id) =>
    set((state) => ({
      cameras: state.cameras.filter((c) => c.id !== id),
      activeCamera:
        state.activeCamera?.id === id ? null : state.activeCamera,
    })),

  updateCameraStatus: (id, status) =>
    set((state) => ({
      cameras: state.cameras.map((c) =>
        c.id === id ? { ...c, status } : c
      ),
    })),

  /* ---- Detection zones ---- */

  setDetectionZone: (cameraId, points) =>
    set((state) => ({
      detectionZones: { ...state.detectionZones, [cameraId]: points },
    })),

  clearDetectionZone: (cameraId) =>
    set((state) => {
      const zones = { ...state.detectionZones };
      delete zones[cameraId];
      return { detectionZones: zones };
    }),

  /* ---- Pipeline toggles ---- */

  setPipelineToggles: (toggles) =>
    set({ pipelineToggles: toggles }),
}));
