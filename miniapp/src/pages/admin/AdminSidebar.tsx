import React, { useEffect } from 'react';

export type AdminPage = 'dashboard' | 'types';

interface Props {
  open: boolean;
  active: AdminPage;
  onClose: () => void;
  onNavigate: (page: AdminPage) => void;
  onLogout: () => void;
}

const AdminSidebar: React.FC<Props> = ({ open, active, onClose, onNavigate, onLogout }) => {
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [open, onClose]);

  const go = (p: AdminPage) => {
    onNavigate(p);
    onClose();
  };

  return (
    <>
      <div
        className={`admin-sidebar-overlay ${open ? 'admin-sidebar-overlay--open' : ''}`}
        onClick={onClose}
        aria-hidden={!open}
      />
      <aside className={`admin-sidebar ${open ? 'admin-sidebar--open' : ''}`} aria-hidden={!open}>
        <div className="admin-sidebar-header">
          <span className="admin-sidebar-title">Admin</span>
          <button
            className="admin-sidebar-close"
            onClick={onClose}
            aria-label="Close menu"
          >
            ✕
          </button>
        </div>
        <nav className="admin-sidebar-nav">
          <button
            className={`admin-sidebar-item ${active === 'dashboard' ? 'admin-sidebar-item--active' : ''}`}
            onClick={() => go('dashboard')}
          >
            <span className="admin-sidebar-item-icon">▦</span>
            Sets
          </button>
          <button
            className={`admin-sidebar-item ${active === 'types' ? 'admin-sidebar-item--active' : ''}`}
            onClick={() => go('types')}
          >
            <span className="admin-sidebar-item-icon">◈</span>
            Types
          </button>
          <div className="admin-sidebar-divider" />
          <button
            className="admin-sidebar-item admin-sidebar-item--danger"
            onClick={() => {
              onClose();
              onLogout();
            }}
          >
            <span className="admin-sidebar-item-icon">⏻</span>
            Logout
          </button>
        </nav>
      </aside>
    </>
  );
};

export default AdminSidebar;
