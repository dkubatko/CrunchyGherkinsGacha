import React, { useEffect, useMemo, useState } from 'react';
import { useAdminStore } from '../../stores/useAdminStore';
import { useAdminDataStore } from '../../stores/useAdminDataStore';
import { AdminApiService } from '../../services/adminApi';
import { useAdminRouter } from '../../hooks/useAdminRouter';
import AdminLoginPage from './AdminLoginPage';
import AdminDashboardPage from './AdminDashboardPage';
import AdminSetDetailPage from './AdminSetDetailPage';
import AdminTypesPage from './AdminTypesPage';
import AdminSidebar, { type AdminPage } from './AdminSidebar';
import './Admin.css';

const PAGE_TITLES: Record<'sets' | 'types' | 'setDetail', string> = {
  sets: 'Sets',
  types: 'Aspect Types',
  setDetail: 'Set Detail',
};

const AdminApp: React.FC = () => {
  const { isAuthenticated, initialize, logout } = useAdminStore();
  const resetData = useAdminDataStore((s) => s.resetData);
  const { route, navigate } = useAdminRouter();
  const [validating, setValidating] = useState(true);
  const [sidebarOpen, setSidebarOpen] = useState(false);

  useEffect(() => {
    initialize();
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

  // Lock viewport zoom while admin is mounted.
  useEffect(() => {
    const viewportEl = document.querySelector('meta[name="viewport"]');
    if (!viewportEl) return;
    const previous = viewportEl.getAttribute('content');
    viewportEl.setAttribute(
      'content',
      'width=device-width, initial-scale=1, maximum-scale=1, user-scalable=no',
    );
    return () => {
      if (previous) viewportEl.setAttribute('content', previous);
    };
  }, []);

  // If the URL has no admin hash, normalize to /sets so back-button has somewhere to go.
  useEffect(() => {
    if (!isAuthenticated || validating) return;
    if (!window.location.hash || window.location.hash === '#' || window.location.hash === '#/') {
      navigate({ kind: 'sets' }, { replace: true });
    }
  }, [isAuthenticated, validating, navigate]);

  const activePage: AdminPage = useMemo(
    () => (route.kind === 'types' ? 'types' : 'dashboard'),
    [route.kind],
  );

  const pageTitle = PAGE_TITLES[route.kind];

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

  const handleLogout = () => {
    resetData();
    logout();
    navigate({ kind: 'sets' }, { replace: true });
  };

  const handleSidebarNavigate = (page: AdminPage) => {
    if (page === 'dashboard') navigate({ kind: 'sets' });
    if (page === 'types') navigate({ kind: 'types' });
  };

  return (
    <div className="admin-container">
      <header className="admin-header">
        <div className="admin-header-left">
          <button
            className="admin-hamburger"
            onClick={() => setSidebarOpen(true)}
            aria-label="Open menu"
          >
            <span />
            <span />
            <span />
          </button>
          {route.kind === 'setDetail' && (
            <button
              className="admin-back-btn"
              onClick={() => navigate({ kind: 'sets' })}
              aria-label="Back to sets"
              title="Back"
            >
              <svg viewBox="0 0 24 24" aria-hidden="true" focusable="false" width="18" height="18">
                <path d="M15 6l-6 6 6 6" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" fill="none" />
              </svg>
            </button>
          )}
          <h1 className="admin-title">{pageTitle}</h1>
        </div>
      </header>

      <AdminSidebar
        open={sidebarOpen}
        active={activePage}
        onClose={() => setSidebarOpen(false)}
        onNavigate={handleSidebarNavigate}
        onLogout={handleLogout}
      />

      {route.kind === 'sets' && (
        <AdminDashboardPage
          onSelectSet={(s) =>
            navigate({ kind: 'setDetail', setId: s.id, seasonId: s.season_id })
          }
        />
      )}

      {route.kind === 'types' && (
        <AdminTypesPage
          onJumpToAspect={(setId, seasonId) =>
            navigate({ kind: 'setDetail', setId, seasonId })
          }
        />
      )}

      {route.kind === 'setDetail' && (
        <AdminSetDetailPage
          setId={route.setId}
          seasonId={route.seasonId}
          onSetDeleted={() => navigate({ kind: 'sets' })}
        />
      )}
    </div>
  );
};

export default AdminApp;
