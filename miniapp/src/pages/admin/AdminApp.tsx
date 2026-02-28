import React, { useEffect, useState } from 'react';
import { useAdminStore } from '../../stores/useAdminStore';
import { AdminApiService } from '../../services/adminApi';
import AdminLoginPage from './AdminLoginPage';
import AdminDashboardPage from './AdminDashboardPage';
import AdminSetDetailPage from './AdminSetDetailPage';
import type { AdminSet } from '../../types/admin';
import './Admin.css';

type AdminView =
  | { page: 'dashboard' }
  | { page: 'setDetail'; set: AdminSet };

const AdminApp: React.FC = () => {
  const { isAuthenticated, initialize, logout } = useAdminStore();
  const [view, setView] = useState<AdminView>({ page: 'dashboard' });
  const [validating, setValidating] = useState(true);

  useEffect(() => {
    initialize();

    // Validate existing token with the server
    const token = localStorage.getItem('admin_token');
    if (token) {
      AdminApiService.getMe()
        .then(() => setValidating(false))
        .catch(() => {
          logout();
          setValidating(false);
        });
    } else {
      setValidating(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    const viewportEl = document.querySelector('meta[name="viewport"]');
    if (!viewportEl) {
      return;
    }

    const previous = viewportEl.getAttribute('content');
    viewportEl.setAttribute(
      'content',
      'width=device-width, initial-scale=1, maximum-scale=1, user-scalable=no',
    );

    return () => {
      if (previous) {
        viewportEl.setAttribute('content', previous);
      }
    };
  }, []);

  if (validating) {
    return (
      <div className="admin-container">
        <div className="admin-loading">Validating session…</div>
      </div>
    );
  }

  if (!isAuthenticated) {
    return <AdminLoginPage />;
  }

  return (
    <div className="admin-container">
      <header className="admin-header">
        <div className="admin-header-left">
          {view.page !== 'dashboard' && (
            <button
              className="admin-back-btn"
              onClick={() => setView({ page: 'dashboard' })}
            >
              ← Back
            </button>
          )}
          <h1 className="admin-title">Modifier Admin</h1>
        </div>
        <button className="admin-logout-btn" onClick={logout}>
          Logout
        </button>
      </header>

      {view.page === 'dashboard' && (
        <AdminDashboardPage
          onSelectSet={(set) => setView({ page: 'setDetail', set })}
        />
      )}

      {view.page === 'setDetail' && (
        <AdminSetDetailPage
          set={view.set}
          onSetUpdated={(updatedSet) =>
            setView({ page: 'setDetail', set: updatedSet })
          }
        />
      )}
    </div>
  );
};

export default AdminApp;
