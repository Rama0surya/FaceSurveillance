/**
 * AlertToast — floating notification toasts for new alerts.
 * - Position: fixed, top-right, z-50
 * - Auto-dismiss after 5s
 * - Max 3 visible toasts
 * - Click → navigate to alerts page
 * - Sound for critical alerts
 */

import { useEffect, useRef, useState, useCallback } from 'react';
import { ShieldAlert, AlertTriangle, Info, X } from 'lucide-react';
import { useCameraStore } from '@/store/cameraStore';
import type { Alert } from '@/store/cameraStore';

interface ToastItem {
  id: string;
  alert: Alert;
  severity: string;
  leaving: boolean;
}

export default function AlertToast() {
  const alerts = useCameraStore((s) => s.alerts);
  const setActivePage = useCameraStore((s) => s.setActivePage);
  const [toasts, setToasts] = useState<ToastItem[]>([]);
  const prevLen = useRef(alerts.length);
  const audioCtx = useRef<AudioContext | null>(null);

  const playBeep = useCallback(() => {
    try {
      if (!audioCtx.current) audioCtx.current = new AudioContext();
      const ctx = audioCtx.current;
      const osc = ctx.createOscillator();
      const gain = ctx.createGain();
      osc.connect(gain);
      gain.connect(ctx.destination);
      osc.type = 'sine';
      osc.frequency.setValueAtTime(880, ctx.currentTime);
      gain.gain.setValueAtTime(0.3, ctx.currentTime);
      gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + 0.3);
      osc.start(ctx.currentTime);
      osc.stop(ctx.currentTime + 0.3);
    } catch { /* silent */ }
  }, []);

  const dismiss = useCallback((id: string) => {
    setToasts((prev) => prev.map((t) => t.id === id ? { ...t, leaving: true } : t));
    setTimeout(() => {
      setToasts((prev) => prev.filter((t) => t.id !== id));
    }, 300);
  }, []);

  useEffect(() => {
    if (alerts.length > prevLen.current) {
      const newAlerts = alerts.slice(0, alerts.length - prevLen.current);
      for (const alert of newAlerts) {
        const severity = alert.emotion === 'angry' || alert.emotion === 'fear' ? 'critical' : 'info';
        const id = `toast-${Date.now()}-${alert.id}`;
        setToasts((prev) => [{ id, alert, severity, leaving: false }, ...prev].slice(0, 3));
        if (severity === 'critical') playBeep();
        setTimeout(() => dismiss(id), 5000);
      }
    }
    prevLen.current = alerts.length;
  }, [alerts.length]); // eslint-disable-line react-hooks/exhaustive-deps

  if (toasts.length === 0) return null;

  return (
    <div className="alert-toast-container">
      {toasts.map((t) => (
        <div
          key={t.id}
          className={`alert-toast alert-toast--${t.severity} ${t.leaving ? 'alert-toast--leaving' : ''}`}
          onClick={() => { dismiss(t.id); setActivePage('alerts'); }}
        >
          <div className="alert-toast__icon">
            {t.severity === 'critical' ? <ShieldAlert size={18} /> : t.severity === 'warning' ? <AlertTriangle size={18} /> : <Info size={18} />}
          </div>
          <div className="alert-toast__body">
            <p className="alert-toast__title">
              {t.severity === 'critical' ? 'Critical Alert' : 'New Alert'}
            </p>
            <p className="alert-toast__msg">
              {t.alert.emotion} — {t.alert.camera_name}
            </p>
          </div>
          <button className="alert-toast__close" onClick={(e) => { e.stopPropagation(); dismiss(t.id); }}>
            <X size={14} />
          </button>
        </div>
      ))}
    </div>
  );
}
