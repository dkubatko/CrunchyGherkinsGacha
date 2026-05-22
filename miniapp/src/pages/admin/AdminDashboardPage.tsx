import React, { useEffect, useRef, useState } from 'react';
import { AdminApiService } from '../../services/adminApi';
import { useAdminDataStore } from '../../stores/useAdminDataStore';
import AdminPopover from './AdminPopover';
import type { AdminSet, AdminSetCreate } from '../../types/admin';
import './Admin.css';

interface Props {
  onSelectSet: (set: AdminSet) => void;
}

const SCROLL_KEY_PREFIX = 'admin:sets:';

const AdminDashboardPage: React.FC<Props> = ({ onSelectSet }) => {
  const seasons = useAdminDataStore((s) => s.seasons);
  const selectedSeason = useAdminDataStore((s) => s.selectedSeason);
  const setSelectedSeason = useAdminDataStore((s) => s.setSelectedSeason);
  const setsBySeason = useAdminDataStore((s) => s.setsBySeason);
  const loadingSeasons = useAdminDataStore((s) => s.loadingSeasons);
  const loadingSets = useAdminDataStore((s) => s.loadingSets);
  const ensureSeasons = useAdminDataStore((s) => s.ensureSeasons);
  const ensureSets = useAdminDataStore((s) => s.ensureSets);
  const applySetUpdate = useAdminDataStore((s) => s.applySetUpdate);
  const applySetInsert = useAdminDataStore((s) => s.applySetInsert);
  const setScroll = useAdminDataStore((s) => s.setScroll);
  const getScroll = useAdminDataStore((s) => s.getScroll);

  const [error, setError] = useState('');
  const [showCreateForm, setShowCreateForm] = useState(false);
  const [newSet, setNewSet] = useState<AdminSetCreate>({
    name: '',
    source: 'all',
    description: '',
    active: true,
  });
  const [creating, setCreating] = useState(false);
  const [seasonAnchor, setSeasonAnchor] = useState<HTMLElement | null>(null);
  const [sourceAnchor, setSourceAnchor] = useState<HTMLElement | null>(null);

  const scrollRef = useRef<HTMLDivElement>(null);

  // Hydrate seasons once.
  useEffect(() => {
    ensureSeasons().catch((err) =>
      setError(err instanceof Error ? err.message : 'Failed to load seasons'),
    );
  }, [ensureSeasons]);

  // Hydrate sets whenever the selected season changes.
  useEffect(() => {
    if (selectedSeason == null) return;
    ensureSets(selectedSeason).catch((err) =>
      setError(err instanceof Error ? err.message : 'Failed to load sets'),
    );
  }, [selectedSeason, ensureSets]);

  const sets: AdminSet[] | undefined =
    selectedSeason == null ? undefined : setsBySeason[selectedSeason];
  const loading =
    loadingSeasons ||
    (selectedSeason != null && (loadingSets[selectedSeason] ?? false)) ||
    (selectedSeason != null && sets === undefined);

  // Restore scroll position after sets render.
  useEffect(() => {
    if (!sets || !scrollRef.current) return;
    const key = `${SCROLL_KEY_PREFIX}${selectedSeason}`;
    const saved = getScroll(key);
    if (saved > 0) {
      scrollRef.current.scrollTop = saved;
    }
  }, [sets, selectedSeason, getScroll]);

  // Persist scroll position on unmount + on scroll (throttled by RAF).
  useEffect(() => {
    const el = scrollRef.current;
    if (!el || selectedSeason == null) return;
    let raf = 0;
    const onScroll = () => {
      if (raf) return;
      raf = requestAnimationFrame(() => {
        raf = 0;
        setScroll(`${SCROLL_KEY_PREFIX}${selectedSeason}`, el.scrollTop);
      });
    };
    el.addEventListener('scroll', onScroll, { passive: true });
    return () => {
      el.removeEventListener('scroll', onScroll);
      if (raf) cancelAnimationFrame(raf);
      setScroll(`${SCROLL_KEY_PREFIX}${selectedSeason}`, el.scrollTop);
    };
  }, [selectedSeason, sets, setScroll]);

  const handleToggleActive = async (set: AdminSet) => {
    const rollback = applySetUpdate(set.season_id, set.id, { active: !set.active });
    try {
      await AdminApiService.updateSet(set.season_id, set.id, { active: !set.active });
    } catch (err) {
      rollback();
      setError(err instanceof Error ? err.message : 'Failed to update set');
    }
  };

  const handleCreateSet = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedSeason || !newSet.name.trim()) return;
    setCreating(true);
    setError('');
    try {
      const created = await AdminApiService.createSet(selectedSeason, newSet);
      applySetInsert(created);
      setNewSet({ name: '', source: 'all', description: '', active: true });
      setShowCreateForm(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to create set');
    } finally {
      setCreating(false);
    }
  };

  return (
    <div className="admin-content">
      <div className="admin-toolbar">
        <button
          type="button"
          className="admin-dropdown-trigger"
          onClick={(e) => setSeasonAnchor(seasonAnchor ? null : e.currentTarget)}
          aria-haspopup="listbox"
          aria-expanded={!!seasonAnchor}
        >
          <span>Season {selectedSeason ?? '—'}</span>
          <span className="admin-dropdown-caret" aria-hidden="true">▾</span>
        </button>
        {seasonAnchor && (
          <AdminPopover
            anchor={seasonAnchor}
            onClose={() => setSeasonAnchor(null)}
            matchAnchorWidth
          >
            {(seasons ?? []).map((s) => (
              <button
                key={s}
                type="button"
                className={`admin-popover-item ${s === selectedSeason ? 'admin-popover-item--selected' : ''}`}
                onClick={() => {
                  setSelectedSeason(s);
                  setSeasonAnchor(null);
                }}
              >
                Season {s}
              </button>
            ))}
          </AdminPopover>
        )}
        <button
          className="admin-btn admin-btn-secondary admin-btn-sm"
          onClick={() => setShowCreateForm(!showCreateForm)}
        >
          {showCreateForm ? 'Cancel' : '+ New Set'}
        </button>
      </div>

      {showCreateForm && (
        <form onSubmit={handleCreateSet} className="admin-create-form">
          <div className="admin-create-form-row">
            <input
              type="text"
              placeholder="Set name"
              value={newSet.name}
              onChange={(e) => setNewSet({ ...newSet, name: e.target.value })}
              required
            />
            <button
              type="button"
              className="admin-dropdown-trigger"
              onClick={(e) => setSourceAnchor(sourceAnchor ? null : e.currentTarget)}
              aria-haspopup="listbox"
              aria-expanded={!!sourceAnchor}
            >
              <span>{newSet.source === 'roll' ? 'Roll Only' : 'All'}</span>
              <span className="admin-dropdown-caret" aria-hidden="true">▾</span>
            </button>
            {sourceAnchor && (
              <AdminPopover
                anchor={sourceAnchor}
                onClose={() => setSourceAnchor(null)}
                matchAnchorWidth
              >
                {[
                  { value: 'all', label: 'All' },
                  { value: 'roll', label: 'Roll Only' },
                ].map((opt) => (
                  <button
                    key={opt.value}
                    type="button"
                    className={`admin-popover-item ${newSet.source === opt.value ? 'admin-popover-item--selected' : ''}`}
                    onClick={() => {
                      setNewSet({ ...newSet, source: opt.value });
                      setSourceAnchor(null);
                    }}
                  >
                    {opt.label}
                  </button>
                ))}
              </AdminPopover>
            )}
            <button
              type="submit"
              className="admin-btn admin-btn-primary admin-btn-sm"
              disabled={creating}
            >
              {creating ? 'Creating (generating icon…)' : 'Create'}
            </button>
          </div>
          <input
            type="text"
            placeholder="Description (optional)"
            value={newSet.description}
            onChange={(e) => setNewSet({ ...newSet, description: e.target.value })}
            className="admin-create-form-desc"
          />
        </form>
      )}

      {error && <div className="admin-error">{error}</div>}
      {loading ? (
        <div className="admin-loading">Loading sets…</div>
      ) : !sets || sets.length === 0 ? (
        <div className="admin-empty">No sets found for this season.</div>
      ) : (
        <div className="admin-set-grid-scroll" ref={scrollRef}>
          <div className="admin-set-grid">
            {sets.map((set) => (
              <div
                key={set.id}
                className={`admin-set-card ${!set.active ? 'admin-set-card--inactive' : ''}`}
                onClick={() => onSelectSet(set)}
              >
                <div className="admin-set-card-header">
                  <div className="admin-set-card-title-row">
                    {set.slot_icon_b64 ? (
                      <img
                        className="admin-set-card-icon"
                        src={`data:image/jpeg;base64,${set.slot_icon_b64}`}
                        alt={set.name}
                      />
                    ) : (
                      <div className="admin-set-card-icon admin-set-card-icon--placeholder" />
                    )}
                    <h3>{set.name}</h3>
                  </div>
                  <button
                    className={`admin-toggle ${set.active ? 'admin-toggle--on' : ''}`}
                    onClick={(e) => {
                      e.stopPropagation();
                      handleToggleActive(set);
                    }}
                    title={set.active ? 'Deactivate' : 'Activate'}
                  >
                    <span className="admin-toggle-thumb" />
                  </button>
                </div>
                <div className="admin-set-card-meta">
                  <span>#{set.id}</span>
                  <span className="admin-set-meta-sep">·</span>
                  <span>{set.source}</span>
                  <span className="admin-set-meta-sep">·</span>
                  <span>{set.aspect_count} aspects</span>
                </div>
                {set.description && (
                  <p className="admin-set-card-desc">{set.description}</p>
                )}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
};

export default AdminDashboardPage;
