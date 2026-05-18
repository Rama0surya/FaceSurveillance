/**
 * AlertsPage — full alerts management with 3 tabs:
 *   1. Live Alerts (real-time from Zustand)
 *   2. Alert History (fetched from API)
 *   3. Alert Rules (CRUD)
 */

import { useState, useEffect, useRef, useCallback } from 'react';
import {
  Bell, CheckCheck, AlertTriangle, Info, ShieldAlert,
  Plus, Pencil, Trash2, X, ChevronLeft, ChevronRight,
  Filter, Camera, Clock,
} from 'lucide-react';
import { useCameraStore } from '@/store/cameraStore';
import type { Alert, AlertRule, AlertFull } from '@/store/cameraStore';
import {
  fetchAlerts, fetchAlertRules, createAlertRule, updateAlertRule,
  deleteAlertRule, markAlertRead, markAllAlertsRead,
} from '@/lib/api';

type TabId = 'live' | 'history' | 'rules';

/* ------------------------------------------------------------------ */
/* Severity helpers                                                    */
/* ------------------------------------------------------------------ */

function severityIcon(s: string) {
  switch (s) {
    case 'critical': return <ShieldAlert size={16} className="alerts-severity-icon--critical" />;
    case 'warning':  return <AlertTriangle size={16} className="alerts-severity-icon--warning" />;
    default:         return <Info size={16} className="alerts-severity-icon--info" />;
  }
}

function severityLabel(s: string) {
  return s.charAt(0).toUpperCase() + s.slice(1);
}

function conditionText(rule: AlertRule): string {
  const c = rule.condition;
  switch (rule.rule_type) {
    case 'emotion':
      return `Emotion "${c.emotion}" ≥ ${c.threshold ?? 1}`;
    case 'crowd_count':
      return `Crowd ≥ ${c.min_count ?? 0}`;
    case 'age_group':
      return `Age group "${c.age_group}" ≥ ${c.threshold ?? 1}`;
    case 'unknown_face':
      return 'Unknown face detected';
    default:
      return JSON.stringify(c);
  }
}

function fmtTime(ts?: string) {
  if (!ts) return '—';
  const d = new Date(ts);
  return d.toLocaleString('id-ID', { day: '2-digit', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit', second: '2-digit' });
}

/* ================================================================== */
/* AlertsPage                                                          */
/* ================================================================== */

export default function AlertsPage() {
  const [tab, setTab] = useState<TabId>('live');
  const unreadAlertCount = useCameraStore((s) => s.unreadAlertCount);
  const setUnreadAlertCount = useCameraStore((s) => s.setUnreadAlertCount);

  const handleMarkAllRead = async () => {
    try {
      await markAllAlertsRead();
      setUnreadAlertCount(0);
    } catch { /* silent */ }
  };

  return (
    <div className="alerts-page">
      {/* Header */}
      <div className="alerts-page__header">
        <div className="alerts-page__title-row">
          <Bell size={22} />
          <h1 className="alerts-page__title">Alerts</h1>
          {unreadAlertCount > 0 && (
            <span className="alerts-badge alerts-badge--header">{unreadAlertCount > 99 ? '99+' : unreadAlertCount}</span>
          )}
        </div>
        <button className="alerts-btn alerts-btn--secondary" onClick={handleMarkAllRead}>
          <CheckCheck size={15} /> Mark All Read
        </button>
      </div>

      {/* Tabs */}
      <div className="alerts-tabs">
        {([
          { id: 'live' as TabId, label: 'Live Alerts' },
          { id: 'history' as TabId, label: 'Alert History' },
          { id: 'rules' as TabId, label: 'Alert Rules' },
        ]).map((t) => (
          <button
            key={t.id}
            className={`alerts-tabs__btn ${tab === t.id ? 'alerts-tabs__btn--active' : ''}`}
            onClick={() => setTab(t.id)}
          >
            {t.label}
          </button>
        ))}
      </div>

      {/* Tab content */}
      <div className="alerts-page__body">
        {tab === 'live' && <LiveAlertsTab />}
        {tab === 'history' && <AlertHistoryTab />}
        {tab === 'rules' && <AlertRulesTab />}
      </div>
    </div>
  );
}

/* ================================================================== */
/* Tab 1 — Live Alerts                                                 */
/* ================================================================== */

function LiveAlertsTab() {
  const alerts = useCameraStore((s) => s.alerts);
  const listRef = useRef<HTMLDivElement>(null);
  const prevLen = useRef(alerts.length);

  useEffect(() => {
    if (alerts.length > prevLen.current && listRef.current) {
      listRef.current.scrollTo({ top: 0, behavior: 'smooth' });
    }
    prevLen.current = alerts.length;
  }, [alerts.length]);

  if (alerts.length === 0) {
    return (
      <div className="alerts-empty">
        <Bell size={40} strokeWidth={1.2} />
        <p>Tidak ada alert aktif</p>
      </div>
    );
  }

  return (
    <div className="alerts-live" ref={listRef}>
      {alerts.map((a: Alert) => (
        <LiveAlertCard key={a.id} alert={a} />
      ))}
    </div>
  );
}

function LiveAlertCard({ alert }: { alert: Alert }) {
  const emotionSeverity = alert.emotion === 'angry' || alert.emotion === 'fear' ? 'critical' : 'info';
  return (
    <div className={`alerts-card alerts-card--${emotionSeverity}`}>
      <div className="alerts-card__icon">{severityIcon(emotionSeverity)}</div>
      <div className="alerts-card__body">
        <p className="alerts-card__msg">
          Detected <strong>{alert.emotion}</strong> emotion
        </p>
        <div className="alerts-card__meta">
          <span><Camera size={12} /> {alert.camera_name}</span>
          <span><Clock size={12} /> {fmtTime(alert.timestamp)}</span>
        </div>
      </div>
      {alert.snapshot_url && (
        <img src={alert.snapshot_url} alt="" className="alerts-card__thumb" />
      )}
    </div>
  );
}

/* ================================================================== */
/* Tab 2 — Alert History                                               */
/* ================================================================== */

function AlertHistoryTab() {
  const cameras = useCameraStore((s) => s.cameras);
  const markAsRead = useCameraStore((s) => s.markAlertAsRead);
  const [data, setData] = useState<AlertFull[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(0);
  const [severity, setSeverity] = useState('');
  const [cameraId, setCameraId] = useState('');
  const [expanded, setExpanded] = useState<string | null>(null);
  const limit = 15;

  const load = useCallback(async () => {
    try {
      const res = await fetchAlerts({
        severity: severity || undefined,
        camera_id: cameraId || undefined,
        limit,
        offset: page * limit,
      });
      setData(res.data);
      setTotal(res.count);
    } catch {
      setData([]);
      setTotal(0);
    }
  }, [severity, cameraId, page]);

  useEffect(() => { load(); }, [load]);

  const totalPages = Math.max(1, Math.ceil(total / limit));

  const handleRead = async (id: string) => {
    try {
      await markAlertRead(id);
      markAsRead(id);
      setData((prev) => prev.map((a) => a.id === id ? { ...a, is_read: true } : a));
    } catch { /* silent */ }
  };

  return (
    <div className="alerts-history">
      {/* Filters */}
      <div className="alerts-history__filters">
        <Filter size={15} />
        <select value={severity} onChange={(e) => { setSeverity(e.target.value); setPage(0); }} className="alerts-select">
          <option value="">All Severity</option>
          <option value="critical">Critical</option>
          <option value="warning">Warning</option>
          <option value="info">Info</option>
        </select>
        <select value={cameraId} onChange={(e) => { setCameraId(e.target.value); setPage(0); }} className="alerts-select">
          <option value="">All Cameras</option>
          {cameras.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
        </select>
      </div>

      {/* Table */}
      <div className="alerts-table-wrap">
        <table className="alerts-table">
          <thead>
            <tr>
              <th>Severity</th><th>Type</th><th>Message</th><th>Camera</th><th>Time</th><th>Status</th><th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {data.length === 0 && (
              <tr><td colSpan={7} className="alerts-table__empty">No alerts found</td></tr>
            )}
            {data.map((a) => (
              <>
                <tr key={a.id} className={`alerts-table__row ${!a.is_read ? 'alerts-table__row--unread' : ''}`} onClick={() => setExpanded(expanded === a.id ? null : a.id)}>
                  <td>{severityIcon(a.severity)} <span className={`alerts-severity-badge alerts-severity-badge--${a.severity}`}>{severityLabel(a.severity)}</span></td>
                  <td>{a.alert_type}</td>
                  <td className="alerts-table__msg-cell">{a.message}</td>
                  <td>{a.camera_id}</td>
                  <td className="alerts-table__time">{fmtTime(a.created_at)}</td>
                  <td>{a.is_read ? <span className="alerts-status alerts-status--read">Read</span> : <span className="alerts-status alerts-status--unread">Unread</span>}</td>
                  <td>
                    {!a.is_read && (
                      <button className="alerts-btn alerts-btn--xs" onClick={(e) => { e.stopPropagation(); handleRead(a.id); }}>Mark Read</button>
                    )}
                  </td>
                </tr>
                {expanded === a.id && (
                  <tr key={`${a.id}-detail`} className="alerts-table__detail-row">
                    <td colSpan={7}>
                      <div className="alerts-table__detail">
                        <strong>Metadata:</strong>
                        <pre>{JSON.stringify(a.metadata, null, 2)}</pre>
                        <p><strong>Resolved:</strong> {a.is_resolved ? 'Yes' : 'No'}</p>
                      </div>
                    </td>
                  </tr>
                )}
              </>
            ))}
          </tbody>
        </table>
      </div>

      {/* Pagination */}
      <div className="alerts-pagination">
        <button disabled={page === 0} onClick={() => setPage(page - 1)} className="alerts-btn alerts-btn--icon"><ChevronLeft size={16} /></button>
        <span className="alerts-pagination__label">Page {page + 1} of {totalPages}</span>
        <button disabled={page >= totalPages - 1} onClick={() => setPage(page + 1)} className="alerts-btn alerts-btn--icon"><ChevronRight size={16} /></button>
      </div>
    </div>
  );
}

/* ================================================================== */
/* Tab 3 — Alert Rules                                                 */
/* ================================================================== */

const EMPTY_RULE: Omit<AlertRule, 'id' | 'created_at'> = {
  name: '',
  rule_type: 'emotion',
  condition: { emotion: 'angry', threshold: 1 },
  severity: 'warning',
  camera_id: null,
  is_active: true,
  cooldown_seconds: 60,
};

function AlertRulesTab() {
  const cameras = useCameraStore((s) => s.cameras);
  const [rules, setRules] = useState<AlertRule[]>([]);
  const [modal, setModal] = useState(false);
  const [editing, setEditing] = useState<AlertRule | null>(null);
  const [form, setForm] = useState<Omit<AlertRule, 'id' | 'created_at'>>(EMPTY_RULE);

  const load = useCallback(async () => {
    try { setRules(await fetchAlertRules()); } catch { /* silent */ }
  }, []);

  useEffect(() => { load(); }, [load]);

  const openAdd = () => { setEditing(null); setForm({ ...EMPTY_RULE }); setModal(true); };
  const openEdit = (r: AlertRule) => {
    setEditing(r);
    setForm({ name: r.name, rule_type: r.rule_type, condition: { ...r.condition }, severity: r.severity, camera_id: r.camera_id, is_active: r.is_active, cooldown_seconds: r.cooldown_seconds });
    setModal(true);
  };

  const handleSave = async () => {
    try {
      if (editing) {
        await updateAlertRule(editing.id, form);
      } else {
        await createAlertRule(form);
      }
      setModal(false);
      load();
    } catch { /* silent */ }
  };

  const handleDelete = async (id: string) => {
    if (!confirm('Delete this rule?')) return;
    try { await deleteAlertRule(id); load(); } catch { /* silent */ }
  };

  const handleToggle = async (r: AlertRule) => {
    try { await updateAlertRule(r.id, { is_active: !r.is_active }); load(); } catch { /* silent */ }
  };

  const updateCondition = (key: string, val: string | number) => {
    setForm((f) => ({ ...f, condition: { ...f.condition, [key]: val } }));
  };

  const handleTypeChange = (type: AlertRule['rule_type']) => {
    let cond: Record<string, any> = {};
    if (type === 'emotion') cond = { emotion: 'angry', threshold: 1 };
    else if (type === 'crowd_count') cond = { min_count: 5 };
    else if (type === 'age_group') cond = { age_group: 'anak', threshold: 1 };
    else cond = {};
    setForm((f) => ({ ...f, rule_type: type, condition: cond }));
  };

  return (
    <div className="alerts-rules">
      <div className="alerts-rules__header">
        <button className="alerts-btn alerts-btn--primary" onClick={openAdd}><Plus size={15} /> Add Rule</button>
      </div>

      {rules.length === 0 && (
        <div className="alerts-empty"><ShieldAlert size={40} strokeWidth={1.2} /><p>No alert rules configured</p></div>
      )}

      <div className="alerts-rules__list">
        {rules.map((r) => (
          <div key={r.id} className={`alerts-rule-card ${!r.is_active ? 'alerts-rule-card--inactive' : ''}`}>
            <div className="alerts-rule-card__top">
              <span className="alerts-rule-card__name">{r.name}</span>
              <span className={`alerts-severity-badge alerts-severity-badge--${r.severity}`}>{severityLabel(r.severity)}</span>
            </div>
            <p className="alerts-rule-card__condition">{conditionText(r)}</p>
            <div className="alerts-rule-card__meta">
              <span>Type: {r.rule_type}</span>
              <span>Cooldown: {r.cooldown_seconds}s</span>
            </div>
            <div className="alerts-rule-card__actions">
              <label className="alerts-toggle">
                <input type="checkbox" checked={r.is_active} onChange={() => handleToggle(r)} />
                <span className="alerts-toggle__slider" />
              </label>
              <button className="alerts-btn alerts-btn--icon" onClick={() => openEdit(r)}><Pencil size={14} /></button>
              <button className="alerts-btn alerts-btn--icon alerts-btn--danger" onClick={() => handleDelete(r.id)}><Trash2 size={14} /></button>
            </div>
          </div>
        ))}
      </div>

      {/* Modal */}
      {modal && (
        <div className="alerts-modal-overlay" onClick={() => setModal(false)}>
          <div className="alerts-modal" onClick={(e) => e.stopPropagation()}>
            <div className="alerts-modal__header">
              <h3>{editing ? 'Edit Rule' : 'Add Rule'}</h3>
              <button className="alerts-btn alerts-btn--icon" onClick={() => setModal(false)}><X size={18} /></button>
            </div>
            <div className="alerts-modal__body">
              <label className="alerts-field">
                <span>Name</span>
                <input type="text" value={form.name} onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))} placeholder="Rule name" />
              </label>
              <label className="alerts-field">
                <span>Rule Type</span>
                <select value={form.rule_type} onChange={(e) => handleTypeChange(e.target.value as AlertRule['rule_type'])}>
                  <option value="emotion">Emotion</option>
                  <option value="crowd_count">Crowd Count</option>
                  <option value="age_group">Age Group</option>
                  <option value="unknown_face">Unknown Face</option>
                </select>
              </label>

              {/* Dynamic condition fields */}
              {form.rule_type === 'emotion' && (
                <>
                  <label className="alerts-field">
                    <span>Emotion</span>
                    <select value={form.condition.emotion ?? 'angry'} onChange={(e) => updateCondition('emotion', e.target.value)}>
                      {['angry', 'fear', 'sad', 'happy', 'neutral'].map((em) => <option key={em} value={em}>{em}</option>)}
                    </select>
                  </label>
                  <label className="alerts-field">
                    <span>Threshold</span>
                    <input type="number" min={1} value={form.condition.threshold ?? 1} onChange={(e) => updateCondition('threshold', Number(e.target.value))} />
                  </label>
                </>
              )}
              {form.rule_type === 'crowd_count' && (
                <label className="alerts-field">
                  <span>Min Count</span>
                  <input type="number" min={1} value={form.condition.min_count ?? 5} onChange={(e) => updateCondition('min_count', Number(e.target.value))} />
                </label>
              )}
              {form.rule_type === 'age_group' && (
                <>
                  <label className="alerts-field">
                    <span>Age Group</span>
                    <select value={form.condition.age_group ?? 'anak'} onChange={(e) => updateCondition('age_group', e.target.value)}>
                      {['anak', 'remaja', 'dewasa', 'lansia'].map((ag) => <option key={ag} value={ag}>{ag}</option>)}
                    </select>
                  </label>
                  <label className="alerts-field">
                    <span>Threshold</span>
                    <input type="number" min={1} value={form.condition.threshold ?? 1} onChange={(e) => updateCondition('threshold', Number(e.target.value))} />
                  </label>
                </>
              )}

              <label className="alerts-field">
                <span>Severity</span>
                <select value={form.severity} onChange={(e) => setForm((f) => ({ ...f, severity: e.target.value as AlertRule['severity'] }))}>
                  <option value="info">Info</option>
                  <option value="warning">Warning</option>
                  <option value="critical">Critical</option>
                </select>
              </label>
              <label className="alerts-field">
                <span>Camera</span>
                <select value={form.camera_id ?? ''} onChange={(e) => setForm((f) => ({ ...f, camera_id: e.target.value || null }))}>
                  <option value="">All Cameras</option>
                  {cameras.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
                </select>
              </label>
              <label className="alerts-field">
                <span>Cooldown (seconds)</span>
                <input type="number" min={0} value={form.cooldown_seconds} onChange={(e) => setForm((f) => ({ ...f, cooldown_seconds: Number(e.target.value) }))} />
              </label>
              <label className="alerts-field alerts-field--row">
                <span>Active</span>
                <input type="checkbox" checked={form.is_active} onChange={(e) => setForm((f) => ({ ...f, is_active: e.target.checked }))} />
              </label>
            </div>
            <div className="alerts-modal__footer">
              <button className="alerts-btn alerts-btn--secondary" onClick={() => setModal(false)}>Cancel</button>
              <button className="alerts-btn alerts-btn--primary" onClick={handleSave}>Save</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
