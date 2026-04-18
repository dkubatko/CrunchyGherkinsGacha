import React, { useEffect, useState, useCallback } from 'react';
import { AdminApiService } from '../../services/adminApi';
import type {
  AdminAspectType,
  AdminAspectTypeCreate,
  AdminAspectByType,
  AdminSet,
} from '../../types/admin';
import './Admin.css';

interface Props {
  onJumpToAspect: (set: AdminSet) => void;
  onSeasonChange: (season: number) => void;
}

const AdminTypesPage: React.FC<Props> = ({ onJumpToAspect, onSeasonChange }) => {
  const [types, setTypes] = useState<AdminAspectType[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const [showCreate, setShowCreate] = useState(false);
  const [newName, setNewName] = useState('');
  const [newDesc, setNewDesc] = useState('');
  const [creating, setCreating] = useState(false);

  const [editingId, setEditingId] = useState<number | null>(null);
  const [editName, setEditName] = useState('');
  const [editDesc, setEditDesc] = useState('');
  const [savingEdit, setSavingEdit] = useState(false);

  const [expandedId, setExpandedId] = useState<number | null>(null);
  const [aspectsByType, setAspectsByType] = useState<Record<number, AdminAspectByType[]>>({});
  const [loadingAspects, setLoadingAspects] = useState<number | null>(null);

  const loadTypes = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const data = await AdminApiService.getTypes();
      setTypes(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load types');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadTypes();
  }, [loadTypes]);

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newName.trim()) return;
    setCreating(true);
    setError('');
    try {
      const payload: AdminAspectTypeCreate = { name: newName.trim() };
      if (newDesc.trim()) payload.description = newDesc.trim();
      await AdminApiService.createType(payload);
      setNewName('');
      setNewDesc('');
      setShowCreate(false);
      await loadTypes();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to create type');
    } finally {
      setCreating(false);
    }
  };

  const startEdit = (t: AdminAspectType) => {
    setEditingId(t.id);
    setEditName(t.name);
    setEditDesc(t.description ?? '');
  };

  const saveEdit = async () => {
    if (editingId == null) return;
    setSavingEdit(true);
    setError('');
    try {
      await AdminApiService.updateType(editingId, {
        name: editName.trim() || undefined,
        description: editDesc.trim(),
      });
      setEditingId(null);
      await loadTypes();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to update type');
    } finally {
      setSavingEdit(false);
    }
  };

  const handleDelete = async (t: AdminAspectType) => {
    if (t.usage_count > 0) return;
    if (!window.confirm(`Delete type "${t.name}"?`)) return;
    setError('');
    try {
      await AdminApiService.deleteType(t.id);
      setExpandedId((cur) => (cur === t.id ? null : cur));
      await loadTypes();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to delete type');
    }
  };

  const toggleExpand = async (t: AdminAspectType) => {
    if (expandedId === t.id) {
      setExpandedId(null);
      return;
    }
    setExpandedId(t.id);
    if (!aspectsByType[t.id]) {
      setLoadingAspects(t.id);
      try {
        const data = await AdminApiService.getAspectsByType(t.id);
        setAspectsByType((prev) => ({ ...prev, [t.id]: data }));
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Failed to load aspects for type');
      } finally {
        setLoadingAspects(null);
      }
    }
  };

  const handleJump = async (a: AdminAspectByType) => {
    try {
      const sets = await AdminApiService.getSetsBySeason(a.season_id);
      const target = sets.find((s) => s.id === a.set_id);
      if (target) {
        onSeasonChange(a.season_id);
        onJumpToAspect(target);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to navigate to set');
    }
  };

  // Group aspects by season then set for display
  const groupAspects = (items: AdminAspectByType[]) => {
    const bySeason: Record<number, Record<number, AdminAspectByType[]>> = {};
    for (const a of items) {
      bySeason[a.season_id] = bySeason[a.season_id] ?? {};
      bySeason[a.season_id][a.set_id] = bySeason[a.season_id][a.set_id] ?? [];
      bySeason[a.season_id][a.set_id].push(a);
    }
    return bySeason;
  };

  return (
    <div className="admin-content">
      <div className="admin-toolbar">
        <h2 className="admin-section-heading">Aspect Types</h2>
        <button
          className="admin-btn admin-btn-secondary admin-btn-sm"
          onClick={() => setShowCreate((v) => !v)}
        >
          {showCreate ? 'Cancel' : '+ New Type'}
        </button>
      </div>

      {showCreate && (
        <form onSubmit={handleCreate} className="admin-create-form">
          <div className="admin-create-form-row">
            <input
              type="text"
              placeholder="Type name (e.g. Location)"
              value={newName}
              onChange={(e) => setNewName(e.target.value)}
              required
              autoFocus
            />
            <button
              type="submit"
              className="admin-btn admin-btn-primary admin-btn-sm"
              disabled={creating || !newName.trim()}
            >
              {creating ? 'Creating…' : 'Create'}
            </button>
          </div>
          <input
            type="text"
            placeholder="Description (optional, used to guide image generation)"
            value={newDesc}
            onChange={(e) => setNewDesc(e.target.value)}
            className="admin-create-form-desc"
          />
        </form>
      )}

      {error && <div className="admin-error">{error}</div>}

      {loading ? (
        <div className="admin-loading">Loading types…</div>
      ) : types.length === 0 ? (
        <div className="admin-empty">No types yet. Create one to start tagging aspects.</div>
      ) : (
        <div className="admin-type-card-list">
          {types.map((t) => {
            const isEditing = editingId === t.id;
            const isExpanded = expandedId === t.id;
            const aspects = aspectsByType[t.id] ?? [];
            return (
              <div
                key={t.id}
                className={`admin-type-card ${isExpanded ? 'admin-type-card--expanded' : ''}`}
              >
                <div className="admin-type-card-row">
                  {isEditing ? (
                    <div className="admin-type-card-edit">
                      <input
                        className="admin-type-card-input"
                        value={editName}
                        onChange={(e) => setEditName(e.target.value)}
                        placeholder="Name"
                        autoFocus
                      />
                      <input
                        className="admin-type-card-input admin-type-card-input--desc"
                        value={editDesc}
                        onChange={(e) => setEditDesc(e.target.value)}
                        placeholder="Description"
                      />
                      <div className="admin-type-card-actions">
                        <button
                          className="admin-icon-btn admin-icon-btn--save"
                          onClick={saveEdit}
                          disabled={savingEdit}
                          title="Save"
                        >
                          ✓
                        </button>
                        <button
                          className="admin-icon-btn"
                          onClick={() => setEditingId(null)}
                          title="Cancel"
                        >
                          ✕
                        </button>
                      </div>
                    </div>
                  ) : (
                    <>
                      <button
                        className="admin-type-card-toggle"
                        onClick={() => toggleExpand(t)}
                        aria-expanded={isExpanded}
                        title={isExpanded ? 'Collapse' : 'Expand'}
                      >
                        <span className="admin-type-card-chevron">{isExpanded ? '▾' : '▸'}</span>
                        <span className="admin-type-card-name">{t.name}</span>
                        {t.description && (
                          <span className="admin-type-card-desc">{t.description}</span>
                        )}
                      </button>
                      <div className="admin-type-card-meta">
                        <span className="admin-type-card-count">{t.usage_count}</span>
                        <button
                          className="admin-icon-btn admin-action-icon admin-action-icon--edit"
                          onClick={() => startEdit(t)}
                          title="Edit"
                        >
                          ✎
                        </button>
                        <button
                          className="admin-icon-btn admin-action-icon admin-action-icon--delete"
                          onClick={() => handleDelete(t)}
                          disabled={t.usage_count > 0}
                          title={t.usage_count > 0 ? 'In use — cannot delete' : 'Delete'}
                        >
                          ✕
                        </button>
                      </div>
                    </>
                  )}
                </div>

                {isExpanded && !isEditing && (
                  <div className="admin-type-card-body">
                    {loadingAspects === t.id ? (
                      <div className="admin-loading admin-loading--inline">Loading…</div>
                    ) : aspects.length === 0 ? (
                      <div className="admin-empty admin-empty--inline">
                        No aspects use this type yet.
                      </div>
                    ) : (
                      Object.entries(groupAspects(aspects))
                        .sort(([a], [b]) => Number(b) - Number(a))
                        .map(([seasonId, bySet]) => (
                          <div key={seasonId} className="admin-type-aspects-season">
                            <div className="admin-type-aspects-season-label">
                              Season {seasonId}
                            </div>
                            {Object.entries(bySet).map(([setId, items]) => (
                              <div key={setId} className="admin-type-aspects-set">
                                <div className="admin-type-aspects-set-label">
                                  {items[0].set_name ?? `Set #${setId}`}
                                </div>
                                <div className="admin-type-aspects-list">
                                  {items.map((a) => (
                                    <button
                                      key={a.id}
                                      className={`admin-type-aspect-chip rarity-${a.rarity.toLowerCase()}`}
                                      onClick={() => handleJump(a)}
                                      title={`Open ${a.name} in ${items[0].set_name ?? 'set'}`}
                                    >
                                      {a.name}
                                    </button>
                                  ))}
                                </div>
                              </div>
                            ))}
                          </div>
                        ))
                    )}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
};

export default AdminTypesPage;
