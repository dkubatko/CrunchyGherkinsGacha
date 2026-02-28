import React, { useEffect, useState, useCallback } from 'react';
import { AdminApiService } from '../../services/adminApi';
import type { AdminSet, AdminSetCreate } from '../../types/admin';
import './Admin.css';

interface Props {
  onSelectSet: (set: AdminSet) => void;
}

const AdminDashboardPage: React.FC<Props> = ({ onSelectSet }) => {
  const [seasons, setSeasons] = useState<number[]>([]);
  const [selectedSeason, setSelectedSeason] = useState<number | null>(null);
  const [sets, setSets] = useState<AdminSet[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  // Create-set form state
  const [showCreateForm, setShowCreateForm] = useState(false);
  const [newSet, setNewSet] = useState<AdminSetCreate>({
    name: '',
    source: 'all',
    description: '',
    active: true,
  });
  const [creating, setCreating] = useState(false);

  useEffect(() => {
    AdminApiService.getSeasons()
      .then((s) => {
        setSeasons(s);
        if (s.length > 0) setSelectedSeason(s[s.length - 1]); // default to latest
      })
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false));
  }, []);

  const loadSets = useCallback(async () => {
    if (selectedSeason == null) return;
    setLoading(true);
    setError('');
    try {
      const data = await AdminApiService.getSetsBySeason(selectedSeason);
      setSets(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load sets');
    } finally {
      setLoading(false);
    }
  }, [selectedSeason]);

  useEffect(() => {
    loadSets();
  }, [loadSets]);

  const handleToggleActive = async (set: AdminSet) => {
    try {
      await AdminApiService.updateSet(set.season_id, set.id, { active: !set.active });
      setSets((prev) =>
        prev.map((s) => (s.id === set.id ? { ...s, active: !s.active } : s)),
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to update set');
    }
  };

  const handleCreateSet = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedSeason || !newSet.name.trim()) return;
    setCreating(true);
    try {
      await AdminApiService.createSet(selectedSeason, newSet);
      setNewSet({ name: '', source: 'all', description: '', active: true });
      setShowCreateForm(false);
      await loadSets();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to create set');
    } finally {
      setCreating(false);
    }
  };

  return (
    <div className="admin-content">
      {/* Toolbar: season selector + new-set button */}
      <div className="admin-toolbar">
        <select
          className="admin-season-select"
          value={selectedSeason ?? ''}
          onChange={(e) => setSelectedSeason(Number(e.target.value))}
        >
          {seasons.map((s) => (
            <option key={s} value={s}>
              Season {s}
            </option>
          ))}
        </select>
        <button
          className="admin-btn admin-btn-secondary admin-btn-sm"
          onClick={() => setShowCreateForm(!showCreateForm)}
        >
          {showCreateForm ? 'Cancel' : '+ New Set'}
        </button>
      </div>

      {/* Create-set form */}
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
            <select
              value={newSet.source}
              onChange={(e) => setNewSet({ ...newSet, source: e.target.value })}
            >
              <option value="all">All</option>
              <option value="roll">Roll Only</option>
            </select>
            <button
              type="submit"
              className="admin-btn admin-btn-primary admin-btn-sm"
              disabled={creating}
            >
              {creating ? 'Creating…' : 'Create'}
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

      {/* Set cards */}
      {loading ? (
        <div className="admin-loading">Loading sets…</div>
      ) : sets.length === 0 ? (
        <div className="admin-empty">No sets found for this season.</div>
      ) : (
        <div className="admin-set-grid-scroll">
          <div className="admin-set-grid">
            {sets.map((set) => (
              <div
                key={set.id}
                className={`admin-set-card ${!set.active ? 'admin-set-card--inactive' : ''}`}
                onClick={() => onSelectSet(set)}
              >
                <div className="admin-set-card-header">
                  <h3>{set.name}</h3>
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
                  <span>{set.modifier_count} modifiers</span>
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
