/**
 * SettingsPage — System settings with vertical tab navigation.
 * Tabs: System Info, Model Config, Stream Settings, Storage, About
 */

import { useState, useEffect, useCallback } from 'react';
import {
  Cpu, HardDrive, Monitor, Zap, Server, Info,
  Settings, Sliders, Radio, Database, RefreshCw,
  Check, AlertTriangle, XCircle, ChevronRight,
  Github, FileText, Shield,
} from 'lucide-react';
import {
  fetchSystemInfo,
  updateDetectionConfig,
  fetchHealthCheck,
} from '@/lib/api';

type TabId = 'system' | 'models' | 'stream' | 'storage' | 'about';

interface TabItem { id: TabId; icon: React.ElementType; label: string; }

const TABS: TabItem[] = [
  { id: 'system', icon: Monitor, label: 'System Info' },
  { id: 'models', icon: Sliders, label: 'Model Configuration' },
  { id: 'stream', icon: Radio, label: 'Stream Settings' },
  { id: 'storage', icon: Database, label: 'Storage' },
  { id: 'about', icon: Info, label: 'About' },
];

/* ------------------------------------------------------------------ */
/* Helper: progress bar color                                          */
/* ------------------------------------------------------------------ */
function usageColor(pct: number) {
  if (pct < 60) return 'var(--settings-green)';
  if (pct < 80) return 'var(--settings-yellow)';
  return 'var(--settings-red)';
}

function usageGradient(pct: number) {
  if (pct < 60) return 'linear-gradient(90deg, #22c55e, #4ade80)';
  if (pct < 80) return 'linear-gradient(90deg, #eab308, #facc15)';
  return 'linear-gradient(90deg, #ef4444, #f87171)';
}

/* ------------------------------------------------------------------ */
/* Main Component                                                      */
/* ------------------------------------------------------------------ */
export default function SettingsPage() {
  const [activeTab, setActiveTab] = useState<TabId>('system');
  const [sysInfo, setSysInfo] = useState<any>(null);
  const [health, setHealth] = useState<any>(null);
  const [loading, setLoading] = useState(true);

  // Model config form state
  const [model, setModel] = useState('VGG-Face');
  const [detector, setDetector] = useState('opencv');
  const [interval, setInterval_] = useState(2.0);
  const [fps, setFps] = useState(5);
  const [saving, setSaving] = useState(false);
  const [saveMsg, setSaveMsg] = useState('');

  // Stream config
  const [rtspTimeout, setRtspTimeout] = useState(10);
  const [jpegQuality, setJpegQuality] = useState(80);
  const [autoReconnect, setAutoReconnect] = useState(true);
  const [maxReconnect, setMaxReconnect] = useState(5);

  // Storage
  const [storageMode, setStorageMode] = useState('local');
  const [snapshotDir, setSnapshotDir] = useState('snapshots');

  const loadData = useCallback(async () => {
    setLoading(true);
    try {
      const [info, h] = await Promise.all([fetchSystemInfo(), fetchHealthCheck()]);
      setSysInfo(info);
      setHealth(h);
      if (info?.models) {
        setModel(info.models.deepface_model);
        setInterval_(info.models.detection_interval);
        setFps(info.models.frame_broadcast_fps);
      }
    } catch {
      // Use fallback mock data when backend is offline
      setSysInfo({
        cpu: { name: 'Unknown', cores_physical: 4, cores_logical: 8, usage_percent: 35, freq_mhz: 3200 },
        memory: { total_gb: 16, available_gb: 8.5, used_gb: 7.5, percent: 47 },
        gpu: { available: false, name: 'No GPU detected', cuda_available: false, cuda_version: null, vram_total_gb: null, vram_used_gb: null, driver_version: null, onnx_gpu_available: false, onnx_providers: ['CPUExecutionProvider'], torch_cuda: false },
        disk: { total_gb: 500, used_gb: 220, free_gb: 280 },
        python: { version: '3.11.0', platform: 'Windows-10' },
        models: { deepface_model: 'VGG-Face', detection_interval: 2.0, frame_broadcast_fps: 5, available_models: ['VGG-Face','Facenet','OpenFace','DeepID','ArcFace','Dlib'], available_detectors: ['opencv','retinaface','mtcnn','ssd','dlib','yolov8'] },
        acceleration: { recommended: 'CPU Only', status: 'fallback', message: 'Tidak ada GPU terdeteksi. Menggunakan CPU.', tips: ['Pertimbangkan menggunakan GPU NVIDIA untuk 5-10x speedup','Tingkatkan DETECTION_INTERVAL_SECONDS jika CPU lambat','Gunakan model yang lebih ringan (opencv detector)'] },
      });
      setHealth({ api_status: 'healthy', supabase_connected: false, active_streams: 0, uptime_seconds: 0, version: '1.0.0' });
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { loadData(); }, [loadData]);

  // Auto-refresh CPU/Memory every 10s when on system tab
  useEffect(() => {
    if (activeTab !== 'system') return;
    const id = window.setInterval(async () => {
      try {
        const info = await fetchSystemInfo();
        setSysInfo(info);
      } catch { /* silent */ }
    }, 10_000);
    return () => clearInterval(id);
  }, [activeTab]);

  async function handleApplyConfig() {
    setSaving(true);
    setSaveMsg('');
    try {
      await updateDetectionConfig({ detection_interval: interval, frame_fps: fps, deepface_model: model });
      setSaveMsg('Configuration saved successfully!');
      setTimeout(() => setSaveMsg(''), 3000);
    } catch { setSaveMsg('Failed to save configuration.'); }
    finally { setSaving(false); }
  }

  function handleResetDefaults() {
    setModel('VGG-Face'); setDetector('opencv'); setInterval_(2.0); setFps(5);
  }

  const cpu = sysInfo?.cpu;
  const mem = sysInfo?.memory;
  const gpu = sysInfo?.gpu;
  const disk = sysInfo?.disk;
  const py = sysInfo?.python;
  const accel = sysInfo?.acceleration;
  const models = sysInfo?.models;
  const diskPct = disk ? Math.round((disk.used_gb / disk.total_gb) * 100) : 0;

  /* ================================================================ */
  /* RENDER TABS                                                       */
  /* ================================================================ */

  function renderSystemInfo() {
    if (loading || !sysInfo) return <div className="sett-loading"><RefreshCw size={20} className="sett-spin" /> Loading system info…</div>;
    return (
      <div className="sett-tab-content">
        {/* Hardware Overview */}
        <div className="sett-card">
          <div className="sett-card__header"><Cpu size={16} /> Hardware Overview</div>
          <div className="sett-hw-grid">
            {/* CPU */}
            <div className="sett-hw-item">
              <div className="sett-hw-item__icon sett-hw-item__icon--blue"><Cpu size={18} /></div>
              <div className="sett-hw-item__info">
                <span className="sett-hw-item__label">CPU</span>
                <span className="sett-hw-item__name">{cpu?.name}</span>
                <span className="sett-hw-item__sub">{cpu?.cores_physical}C / {cpu?.cores_logical}T • {cpu?.freq_mhz?.toFixed(0)} MHz</span>
              </div>
              <div className="sett-hw-item__meter">
                <div className="sett-progress">
                  <div className="sett-progress__fill" style={{ width: `${cpu?.usage_percent}%`, background: usageGradient(cpu?.usage_percent) }} />
                </div>
                <span className="sett-hw-item__pct" style={{ color: usageColor(cpu?.usage_percent) }}>{cpu?.usage_percent}%</span>
              </div>
            </div>
            {/* Memory */}
            <div className="sett-hw-item">
              <div className="sett-hw-item__icon sett-hw-item__icon--purple"><Server size={18} /></div>
              <div className="sett-hw-item__info">
                <span className="sett-hw-item__label">Memory</span>
                <span className="sett-hw-item__name">{mem?.used_gb} / {mem?.total_gb} GB</span>
                <span className="sett-hw-item__sub">Available: {mem?.available_gb} GB</span>
              </div>
              <div className="sett-hw-item__meter">
                <div className="sett-progress">
                  <div className="sett-progress__fill" style={{ width: `${mem?.percent}%`, background: usageGradient(mem?.percent) }} />
                </div>
                <span className="sett-hw-item__pct" style={{ color: usageColor(mem?.percent) }}>{mem?.percent}%</span>
              </div>
            </div>
            {/* Disk */}
            <div className="sett-hw-item">
              <div className="sett-hw-item__icon sett-hw-item__icon--amber"><HardDrive size={18} /></div>
              <div className="sett-hw-item__info">
                <span className="sett-hw-item__label">Disk</span>
                <span className="sett-hw-item__name">{disk?.used_gb} / {disk?.total_gb} GB</span>
                <span className="sett-hw-item__sub">Free: {disk?.free_gb} GB</span>
              </div>
              <div className="sett-hw-item__meter">
                <div className="sett-progress">
                  <div className="sett-progress__fill" style={{ width: `${diskPct}%`, background: usageGradient(diskPct) }} />
                </div>
                <span className="sett-hw-item__pct" style={{ color: usageColor(diskPct) }}>{diskPct}%</span>
              </div>
            </div>
            {/* GPU */}
            <div className="sett-hw-item">
              <div className={`sett-hw-item__icon ${gpu?.available ? 'sett-hw-item__icon--green' : 'sett-hw-item__icon--gray'}`}><Zap size={18} /></div>
              <div className="sett-hw-item__info">
                <span className="sett-hw-item__label">GPU</span>
                <span className="sett-hw-item__name">{gpu?.name}</span>
                {gpu?.vram_total_gb && <span className="sett-hw-item__sub">VRAM: {gpu.vram_used_gb} / {gpu.vram_total_gb} GB</span>}
              </div>
              <div className="sett-gpu-badge-wrap">
                {gpu?.cuda_available
                  ? <span className="sett-badge sett-badge--green"><Check size={12} /> CUDA ✓</span>
                  : <span className="sett-badge sett-badge--red"><XCircle size={12} /> No CUDA</span>}
              </div>
            </div>
          </div>
        </div>

        {/* Acceleration Status */}
        <div className="sett-card">
          <div className="sett-card__header"><Zap size={16} /> Acceleration Status</div>
          <div className="sett-accel">
            <div className={`sett-accel__badge sett-accel__badge--${accel?.status}`}>
              {accel?.status === 'optimal' ? <Check size={20} /> : accel?.status === 'partial' ? <AlertTriangle size={20} /> : <Cpu size={20} />}
              <span>{accel?.recommended}</span>
            </div>
            <p className="sett-accel__msg">{accel?.message}</p>
            <ul className="sett-accel__tips">
              {accel?.tips?.map((t: string, i: number) => <li key={i}><ChevronRight size={12} /> {t}</li>)}
            </ul>
          </div>
        </div>

        {/* Software Environment */}
        <div className="sett-card">
          <div className="sett-card__header"><Info size={16} /> Software Environment</div>
          <div className="sett-env-grid">
            <div className="sett-env-row"><span>Python</span><span>{py?.version}</span></div>
            <div className="sett-env-row"><span>Platform</span><span>{py?.platform}</span></div>
            <div className="sett-env-row"><span>ONNX Providers</span><span>{gpu?.onnx_providers?.join(', ') || 'N/A'}</span></div>
            <div className="sett-env-row"><span>GPU Driver</span><span>{gpu?.driver_version || 'N/A'}</span></div>
            <div className="sett-env-row"><span>CUDA Version</span><span>{gpu?.cuda_version || 'N/A'}</span></div>
          </div>
        </div>
      </div>
    );
  }

  function renderModelConfig() {
    const modelDescriptions: Record<string, string> = {
      'VGG-Face': 'High accuracy, slower — best for quality-first use cases',
      'Facenet': 'Good balance of speed and accuracy (recommended)',
      'OpenFace': 'Lightweight, fast inference — lower accuracy',
      'DeepID': 'Compact model for edge deployment',
      'ArcFace': 'State-of-the-art accuracy, heavier compute',
      'Dlib': 'Classic detector, reliable but not the fastest',
    };
    const detectorDescriptions: Record<string, string> = {
      'opencv': 'Fastest, good for real-time — lower recall',
      'retinaface': 'Best accuracy, heavier compute',
      'mtcnn': 'Good balance, multi-stage detection',
      'ssd': 'Fast single-shot detector',
      'dlib': 'Classic HOG-based, reliable',
      'yolov8': 'Modern YOLO — fast and accurate',
    };

    return (
      <div className="sett-tab-content">
        <div className="sett-card">
          <div className="sett-card__header"><Settings size={16} /> Face Detection</div>
          <div className="sett-form-group">
            <label className="sett-label">Recognition Model</label>
            <select className="sett-select" value={model} onChange={(e) => setModel(e.target.value)}>
              {(models?.available_models ?? ['VGG-Face','Facenet','OpenFace','DeepID','ArcFace','Dlib']).map((m: string) => <option key={m} value={m}>{m}</option>)}
            </select>
            <p className="sett-hint">{modelDescriptions[model] ?? ''}</p>
          </div>
          <div className="sett-form-group">
            <label className="sett-label">Detector Backend</label>
            <select className="sett-select" value={detector} onChange={(e) => setDetector(e.target.value)}>
              {(models?.available_detectors ?? ['opencv','retinaface','mtcnn','ssd','dlib','yolov8']).map((d: string) => <option key={d} value={d}>{d}</option>)}
            </select>
            <p className="sett-hint">{detectorDescriptions[detector] ?? ''}</p>
          </div>
        </div>

        <div className="sett-card">
          <div className="sett-card__header"><Sliders size={16} /> Detection Settings</div>
          <div className="sett-form-group">
            <label className="sett-label">Detection Interval: <strong>{interval.toFixed(1)}s</strong></label>
            <input type="range" className="sett-slider" min={0.5} max={10} step={0.5} value={interval} onChange={(e) => setInterval_(parseFloat(e.target.value))} />
            <div className="sett-slider-labels"><span>0.5s</span><span>10s</span></div>
          </div>
          <div className="sett-form-group">
            <label className="sett-label">Frame Broadcast FPS: <strong>{fps}</strong></label>
            <input type="range" className="sett-slider" min={1} max={30} step={1} value={fps} onChange={(e) => setFps(parseInt(e.target.value))} />
            <div className="sett-slider-labels"><span>1 FPS</span><span>30 FPS</span></div>
          </div>
        </div>

        <div className="sett-actions">
          <button className="sett-btn sett-btn--primary" onClick={handleApplyConfig} disabled={saving}>
            {saving ? <><RefreshCw size={14} className="sett-spin" /> Saving…</> : <><Check size={14} /> Apply Changes</>}
          </button>
          <button className="sett-btn sett-btn--secondary" onClick={handleResetDefaults}><RefreshCw size={14} /> Reset Defaults</button>
          {saveMsg && <span className={`sett-save-msg ${saveMsg.includes('success') ? 'sett-save-msg--ok' : 'sett-save-msg--err'}`}>{saveMsg}</span>}
        </div>
      </div>
    );
  }

  function renderStreamSettings() {
    return (
      <div className="sett-tab-content">
        <div className="sett-card">
          <div className="sett-card__header"><Radio size={16} /> Stream Configuration</div>
          <div className="sett-form-group">
            <label className="sett-label">Default RTSP Timeout (seconds)</label>
            <input type="number" className="sett-input" min={1} max={60} value={rtspTimeout} onChange={(e) => setRtspTimeout(parseInt(e.target.value) || 10)} />
          </div>
          <div className="sett-form-group">
            <label className="sett-label">JPEG Quality for WS Broadcast (1-100)</label>
            <input type="range" className="sett-slider" min={1} max={100} value={jpegQuality} onChange={(e) => setJpegQuality(parseInt(e.target.value))} />
            <div className="sett-slider-labels"><span>1 (Low)</span><span className="sett-slider-val">{jpegQuality}</span><span>100 (Max)</span></div>
          </div>
          <div className="sett-form-group">
            <label className="sett-label">Auto-reconnect on Stream Loss</label>
            <button className={`sett-toggle ${autoReconnect ? 'sett-toggle--on' : ''}`} onClick={() => setAutoReconnect(!autoReconnect)}>
              <span className="sett-toggle__knob" />
            </button>
          </div>
          <div className="sett-form-group">
            <label className="sett-label">Max Reconnect Attempts</label>
            <input type="number" className="sett-input" min={1} max={50} value={maxReconnect} onChange={(e) => setMaxReconnect(parseInt(e.target.value) || 5)} disabled={!autoReconnect} />
          </div>
        </div>
      </div>
    );
  }

  function renderStorage() {
    return (
      <div className="sett-tab-content">
        <div className="sett-card">
          <div className="sett-card__header"><Database size={16} /> Snapshot Storage</div>
          <div className="sett-form-group">
            <label className="sett-label">Storage Mode</label>
            <div className="sett-radio-group">
              <label className={`sett-radio ${storageMode === 'local' ? 'sett-radio--active' : ''}`}>
                <input type="radio" name="storage" value="local" checked={storageMode === 'local'} onChange={() => setStorageMode('local')} />
                <HardDrive size={16} /> Local Storage
              </label>
              <label className={`sett-radio ${storageMode === 'supabase' ? 'sett-radio--active' : ''}`}>
                <input type="radio" name="storage" value="supabase" checked={storageMode === 'supabase'} onChange={() => setStorageMode('supabase')} />
                <Database size={16} /> Supabase
              </label>
            </div>
          </div>
          {storageMode === 'local' && (
            <div className="sett-form-group">
              <label className="sett-label">Local Snapshot Directory</label>
              <input type="text" className="sett-input" value={snapshotDir} onChange={(e) => setSnapshotDir(e.target.value)} />
            </div>
          )}
          <div className="sett-form-group">
            <label className="sett-label">Disk Usage (Snapshots)</label>
            <div className="sett-env-row"><span>Used</span><span>{disk?.used_gb ?? '—'} GB</span></div>
          </div>
          <button className="sett-btn sett-btn--danger" onClick={() => alert('Clean snapshots older than 30 days?')}>
            <XCircle size={14} /> Clean Old Snapshots (&gt; 30 days)
          </button>
        </div>
      </div>
    );
  }

  function renderAbout() {
    return (
      <div className="sett-tab-content">
        <div className="sett-card sett-about-card">
          <div className="sett-about__logo"><Shield size={32} /></div>
          <h2 className="sett-about__title">Face Surveillance Dashboard</h2>
          <p className="sett-about__version">Version {health?.version ?? '1.0.0'}</p>
          <div className="sett-about__divider" />
          <div className="sett-env-grid">
            <div className="sett-env-row"><span>API Status</span><span className={health?.api_status === 'healthy' ? 'sett-text-green' : 'sett-text-red'}>{health?.api_status ?? 'Unknown'}</span></div>
            <div className="sett-env-row"><span>Supabase</span><span className={health?.supabase_connected ? 'sett-text-green' : 'sett-text-red'}>{health?.supabase_connected ? 'Connected' : 'Disconnected'}</span></div>
            <div className="sett-env-row"><span>Active Streams</span><span>{health?.active_streams ?? 0}</span></div>
            <div className="sett-env-row"><span>Uptime</span><span>{health?.uptime_seconds ? `${Math.floor(health.uptime_seconds / 60)} min` : '—'}</span></div>
          </div>
          <div className="sett-about__divider" />
          <div className="sett-about__links">
            <a href="https://github.com" target="_blank" rel="noopener noreferrer" className="sett-about__link"><Github size={16} /> GitHub Repository</a>
            <a href="#" className="sett-about__link"><FileText size={16} /> Documentation</a>
          </div>
          <p className="sett-about__license">Built with FastAPI + DeepFace + React<br />© 2026 DDB Telkom. All rights reserved.</p>
        </div>
      </div>
    );
  }

  const tabRenderers: Record<TabId, () => JSX.Element> = {
    system: renderSystemInfo,
    models: renderModelConfig,
    stream: renderStreamSettings,
    storage: renderStorage,
    about: renderAbout,
  };

  return (
    <div className="sett-page">
      {/* Page Header */}
      <div className="sett-page__header">
        <div className="sett-page__header-left">
          <Settings size={24} className="sett-page__header-icon" />
          <div>
            <h1 className="sett-page__title">Settings</h1>
            <p className="sett-page__subtitle">System configuration & hardware monitoring</p>
          </div>
        </div>
        <button className="sett-btn sett-btn--secondary" onClick={loadData}><RefreshCw size={14} /> Refresh</button>
      </div>

      {/* Body: sidebar tabs + content */}
      <div className="sett-body">
        <nav className="sett-tabs">
          {TABS.map((tab) => {
            const Icon = tab.icon;
            return (
              <button key={tab.id} className={`sett-tabs__item ${activeTab === tab.id ? 'sett-tabs__item--active' : ''}`} onClick={() => setActiveTab(tab.id)}>
                <Icon size={16} />
                <span>{tab.label}</span>
              </button>
            );
          })}
        </nav>
        <div className="sett-content">
          {tabRenderers[activeTab]()}
        </div>
      </div>
    </div>
  );
}
