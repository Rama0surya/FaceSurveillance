/**
 * Sidebar — 52px icon-only vertical navigation.
 * Uses Zustand activePage state for routing.
 */

import { useEffect } from 'react';
import {
  LayoutDashboard,
  Camera,
  BarChart3,
  Image,
  Bell,
  Settings,
  Shield,
} from 'lucide-react';
import { useCameraStore } from '@/store/cameraStore';
import type { ActivePage } from '@/store/cameraStore';
import { fetchUnreadCount } from '@/lib/api';

interface NavItem {
  id: ActivePage;
  icon: React.ElementType;
  label: string;
}

const NAV_ITEMS: NavItem[] = [
  { id: 'dashboard', icon: LayoutDashboard, label: 'Dashboard' },
  { id: 'cameras', icon: Camera, label: 'Cameras' },
  { id: 'analytics', icon: BarChart3, label: 'Analytics' },
  { id: 'snapshots', icon: Image, label: 'Snapshots' },
  { id: 'alerts', icon: Bell, label: 'Alerts' },
  { id: 'settings', icon: Settings, label: 'Settings' },
];

export default function Sidebar() {
  const activePage = useCameraStore((s) => s.activePage);
  const setActivePage = useCameraStore((s) => s.setActivePage);
  const unreadAlertCount = useCameraStore((s) => s.unreadAlertCount);
  const setUnreadAlertCount = useCameraStore((s) => s.setUnreadAlertCount);

  useEffect(() => {
    const poll = async () => {
      try {
        const res = await fetchUnreadCount();
        setUnreadAlertCount(res.count);
      } catch { /* silent */ }
    };
    poll();
    const interval = setInterval(poll, 30_000);
    return () => clearInterval(interval);
  }, [setUnreadAlertCount]);

  return (
    <aside className="sidebar">
      {/* Logo */}
      <div className="sidebar__logo">
        <Shield size={22} className="sidebar__logo-icon" />
      </div>

      {/* Navigation */}
      <nav className="sidebar__nav">
        {NAV_ITEMS.map((item) => {
          const Icon = item.icon;
          const isActive = activePage === item.id;
          const showBadge = item.id === 'alerts' && unreadAlertCount > 0;
          return (
            <button
              key={item.id}
              id={`nav-${item.id}`}
              className={`sidebar__item ${isActive ? 'sidebar__item--active' : ''}`}
              onClick={() => setActivePage(item.id)}
              title={item.label}
            >
              <Icon size={20} />
              {showBadge && (
                <span className="sidebar__badge">
                  {unreadAlertCount > 99 ? '99+' : unreadAlertCount}
                </span>
              )}
              <span className="sidebar__tooltip">{item.label}</span>
            </button>
          );
        })}
      </nav>
    </aside>
  );
}

