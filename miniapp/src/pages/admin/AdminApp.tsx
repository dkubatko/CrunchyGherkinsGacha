import React, { useEffect, useState } from 'react';
import { useAdminStore } from '../../stores/useAdminStore';
import { AdminApiService } from '../../services/adminApi';
import AdminLoginPage from './AdminLoginPage';
import AdminDashboardPage from './AdminDashboardPage';
import AdminSetDetailPage from './AdminSetDetailPage';
import AdminTypesPage from './AdminTypesPage';
import AdminSidebar, { type AdminPage } from './AdminSidebar';
import type { AdminSet } from '../../types/admin';
import './Admin.css';

type AdminView =
  | { page: 'dashboard' }
  | { page: 'types' }
  | { page: 'setDetail'; set: AdminSet };

interface StoredView {
  page: AdminView['page'];
  setId?: number;
  seasonId?: number;
  selectedSeason?: number | null;
}

const VIEW_STORAGE_KEY = 'admin_view';

const readStoredView = (): StoredView | null => {
  try {
    const raw = localStorage.getItem(VIEW_STORAGE_KEY);
    if (!raw) return null;
    return JSON.parse(raw) as StoredView;
  } catch {
    return null;
  }
};

const writeStoredView = (v: StoredView) => {
  try {
    localStorage.setItem(VIEW_STORAGE_KEY, JSON.stringify(v));
  } catch {
    /* ignore */
  }
};

const PAGE_TITLES: Record<AdminView['page'], string> = {
  dashboard: 'Sets',
  types: 'Aspect Types',
  setDetail: 'Set Detail',
};

const AdminApp: React.FC = () => {
  const { isAuthenticated, initialize, logout } = useAdminStore();
  const [view, setView] = useState<AdminView>({ page: 'dashboard' });
  const [validating, setValidating] = useState(true);
  const [selectedSeason, setSelectedSeason] = useState<number | null>(null);
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [restoringView, setRestoringView] = useState(false);

  useEffect(() => {
    initialize();

    // Validate existing token with the server
    const token = localStorage.getItem('admin_token');
    if (token) {
      AdminApiService.getMe()
        .then(async () => {
          // Restore the previously-viewed page on refresh.
          const stored = readStoredView();
          if (stored) {
            if (stored.selectedSeason !== undefined) setSelectedSeason(stored.selectedSeason);
            if (stored.page === 'types') {
              setView({ page: 'types' });
            } else if (stored.page === 'setDetail' && stored.setId && stored.seasonId) {
              setRestoringView(true);
              try {
                const sets = await AdminApiService.getSetsBySeason(stored.seasonId);
                const match = sets.find((s) => s.id === stored.setId);
                if (match) {
                  setView({ page: 'setDetail', set: match });
                }
              } catch {
                /* fallback to dashboard */
              } finally {
                setRestoringView(false);
              }
            }
          }
          setValidating(false);
        })
        .catch(() => {
          logout();
          setValidating(false);
        });
    } else {
      setValidating(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Persist view whenever it changes (auth'd only).
  useEffect(() => {
    if (validating || !isAuthenticated) return;
    const toStore: StoredView = {
      page: view.page,
      selectedSeason,
    };
    if (view.page === 'setDetail') {
      toStore.setId = view.set.id;
      toStore.seasonId = view.set.season_id;
    }
    writeStoredView(toStore);
  }, [view, selectedSeason, validating, isAuthenticated]);

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

  if (validating || restoringView) {
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
    try { localStorage.removeItem(VIEW_STORAGE_KEY); } catch { /* ignore */ }
    logout();
  };

  const navigateTo = (page: AdminPage) => {
    if (page === 'dashboard') setView({ page: 'dashboard' });
    if (page === 'types') setView({ page: 'types' });
  };

  // Active sidebar entry: setDetail counts as Sets
  const activePage: AdminPage = view.page === 'types' ? 'types' : 'dashboard';

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
          {view.page === 'setDetail' && (
            <button
              className="admin-back-btn"
              onClick={() => setView({ page: 'dashboard' })}
            >
              ← Back
            </button>
          )}
          <h1 className="admin-title">{PAGE_TITLES[view.page]}</h1>
        </div>
      </header>

      <AdminSidebar
        open={sidebarOpen}
        active={activePage}
        onClose={() => setSidebarOpen(false)}
        onNavigate={navigateTo}
        onLogout={handleLogout}
      />

      {view.page === 'dashboard' && (
        <AdminDashboardPage
          onSelectSet={(set) => setView({ page: 'setDetail', set })}
          selectedSeason={selectedSeason}
          onSeasonChange={setSelectedSeason}
        />
      )}

      {view.page === 'types' && (
        <AdminTypesPage
          onJumpToAspect={(set) => setView({ page: 'setDetail', set })}
          onSeasonChange={setSelectedSeason}
        />
      )}

      {view.page === 'setDetail' && (
        <AdminSetDetailPage
          set={view.set}
          onSetUpdated={(updatedSet) =>
            setView({ page: 'setDetail', set: updatedSet })
          }
          onSetDeleted={() => setView({ page: 'dashboard' })}
        />
      )}
    </div>
  );
};

export default AdminApp;
