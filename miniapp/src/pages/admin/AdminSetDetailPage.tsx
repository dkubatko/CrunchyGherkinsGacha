import React, { useEffect, useState, useCallback } from 'react';
import { AdminApiService } from '../../services/adminApi';
import type { AdminSet, AdminModifier, AdminModifierCreate } from '../../types/admin';
import './Admin.css';

const RARITIES = ['Common', 'Rare', 'Epic', 'Legendary'];

const EditIcon = () => (
  <svg viewBox="0 0 24 24" aria-hidden="true" focusable="false">
    <path
      d="M12 20h9"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
    />
    <path
      d="M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4 12.5-12.5z"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      fill="none"
    />
  </svg>
);

const DeleteIcon = () => (
  <svg viewBox="0 0 24 24" aria-hidden="true" focusable="false">
    <path
      d="M3 6h18"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
    />
    <path
      d="M8 6V4h8v2"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      fill="none"
    />
    <path
      d="M19 6l-1 14H6L5 6"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      fill="none"
    />
    <path
      d="M10 11v6M14 11v6"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      fill="none"
    />
  </svg>
);

interface Props {
  set: AdminSet;
  onSetUpdated: (set: AdminSet) => void;
}

const AdminSetDetailPage: React.FC<Props> = ({ set, onSetUpdated }) => {
  const [modifiers, setModifiers] = useState<AdminModifier[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [search, setSearch] = useState('');
  const [editingDescription, setEditingDescription] = useState(false);
  const [descriptionDraft, setDescriptionDraft] = useState(set.description ?? '');
  const [savingDescription, setSavingDescription] = useState(false);
  const [draggedModifierId, setDraggedModifierId] = useState<number | null>(null);
  const [dragOverRarity, setDragOverRarity] = useState<string | null>(null);

  // Add modifier form (per-rarity)
  const [newByRarity, setNewByRarity] = useState<Record<string, string>>({
    Common: '',
    Rare: '',
    Epic: '',
    Legendary: '',
  });
  const [addingRarity, setAddingRarity] = useState<string | null>(null);

  // Inline editing
  const [editingId, setEditingId] = useState<number | null>(null);
  const [editName, setEditName] = useState('');

  const loadModifiers = useCallback(async (silent = false) => {
    if (!silent) setLoading(true);
    setError('');
    try {
      const data = await AdminApiService.getModifiers(set.id, set.season_id);
      setModifiers(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load modifiers');
    } finally {
      setLoading(false);
    }
  }, [set.id, set.season_id]);

  useEffect(() => {
    loadModifiers();
  }, [loadModifiers]);

  useEffect(() => {
    setDescriptionDraft(set.description ?? '');
  }, [set.description]);

  const filtered = modifiers.filter(
    (m) => !search || m.name.toLowerCase().includes(search.toLowerCase()),
  );

  const grouped = RARITIES.reduce<Record<string, AdminModifier[]>>((acc, rarity) => {
    acc[rarity] = filtered
      .filter((m) => m.rarity === rarity)
      .sort((a, b) => a.name.localeCompare(b.name, undefined, { sensitivity: 'base' }));
    return acc;
  }, {});

  // ── Handlers ──────────────────────────────────────────────────────────

  const handleSaveDescription = async () => {
    const nextDescription = descriptionDraft.trim();
    if (nextDescription === (set.description ?? '').trim()) {
      setEditingDescription(false);
      return;
    }

    setSavingDescription(true);
    setError('');
    try {
      const updated = await AdminApiService.updateSet(set.season_id, set.id, {
        description: nextDescription,
      });
      onSetUpdated(updated);
      setEditingDescription(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to update description');
    } finally {
      setSavingDescription(false);
    }
  };

  const handleAddModifier = async (rarity: string, e: React.FormEvent) => {
    e.preventDefault();
    const name = (newByRarity[rarity] ?? '').trim();
    if (!name) return;
    setAddingRarity(rarity);
    setError('');
    try {
      const payload: AdminModifierCreate = {
        set_id: set.id,
        season_id: set.season_id,
        name,
        rarity,
      };
      await AdminApiService.createModifier(payload);
      setNewByRarity((prev) => ({ ...prev, [rarity]: '' }));
      await loadModifiers(true);
      onSetUpdated({ ...set, modifier_count: set.modifier_count + 1 });
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to add modifier');
    } finally {
      setAddingRarity(null);
    }
  };

  const handleStartEdit = (mod: AdminModifier) => {
    setEditingId(mod.id);
    setEditName(mod.name);
  };

  const handleSaveEdit = async (modId: number) => {
    setError('');
    try {
      await AdminApiService.updateModifier(modId, {
        name: editName.trim(),
      });
      setEditingId(null);
      await loadModifiers(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to update modifier');
    }
  };

  const handleCancelEdit = () => {
    setEditingId(null);
  };

  const handleDelete = async (mod: AdminModifier) => {
    const warning =
      mod.card_count > 0
        ? `WARNING: ${mod.card_count} card(s) use this modifier.\n\n`
        : '';
    if (!confirm(`${warning}Delete "${mod.name}"?`)) return;
    setError('');
    try {
      await AdminApiService.deleteModifier(mod.id);
      await loadModifiers(true);
      onSetUpdated({ ...set, modifier_count: set.modifier_count - 1 });
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to delete modifier');
    }
  };

  const handleDragStart = (modifierId: number) => {
    setDraggedModifierId(modifierId);
  };

  const handleDragEnd = () => {
    setDraggedModifierId(null);
    setDragOverRarity(null);
  };

  const handleDropRarity = async (targetRarity: string) => {
    if (draggedModifierId == null) return;
    const mod = modifiers.find((m) => m.id === draggedModifierId);
    if (!mod || mod.rarity === targetRarity) {
      handleDragEnd();
      return;
    }

    setError('');
    const prev = modifiers;
    setModifiers((curr) =>
      curr.map((m) => (m.id === draggedModifierId ? { ...m, rarity: targetRarity } : m)),
    );

    try {
      await AdminApiService.updateModifier(draggedModifierId, { rarity: targetRarity });
    } catch (err) {
      setModifiers(prev);
      setError(err instanceof Error ? err.message : 'Failed to move modifier');
    } finally {
      handleDragEnd();
    }
  };

  const getRarityClass = (rarity: string) => `rarity-${rarity.toLowerCase()}`;

  return (
    <div className="admin-content">
      <div className="admin-set-hero">
        <h2 className="admin-set-hero-title">{set.name}</h2>

        <div className="admin-set-hero-meta">
          <span className={`admin-set-status ${set.active ? 'admin-set-status--active' : 'admin-set-status--inactive'}`}>
            {set.active ? 'Active' : 'Inactive'}
          </span>
          <span className="admin-set-meta-sep">·</span>
          <span>Set #{set.id}</span>
          <span className="admin-set-meta-sep">·</span>
          <span>Season {set.season_id}</span>
          <span className="admin-set-meta-sep">·</span>
          <span>{modifiers.length} modifiers</span>
          <span className="admin-set-meta-sep">·</span>
          <span>{set.source}</span>
        </div>

        <div className="admin-set-description">
          {!editingDescription ? (
            <>
              <p className="admin-set-description-text">
                {set.description?.trim() || 'No description yet'}
              </p>
              <button
                className="admin-set-description-edit"
                onClick={() => setEditingDescription(true)}
                aria-label="Edit description"
              >
                <EditIcon />
              </button>
            </>
          ) : (
            <div className="admin-set-description-editing">
              <textarea
                className="admin-set-description-input"
                value={descriptionDraft}
                onChange={(e) => setDescriptionDraft(e.target.value)}
                rows={2}
                maxLength={500}
                autoFocus
              />
              <div className="admin-set-description-actions">
                <button
                  className="admin-btn admin-btn-secondary admin-btn-sm"
                  onClick={() => {
                    setDescriptionDraft(set.description ?? '');
                    setEditingDescription(false);
                  }}
                  disabled={savingDescription}
                >
                  Cancel
                </button>
                <button
                  className="admin-btn admin-btn-primary admin-btn-sm"
                  onClick={handleSaveDescription}
                  disabled={savingDescription}
                >
                  {savingDescription ? 'Saving…' : 'Save'}
                </button>
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Search */}
      <div className="admin-toolbar">
        <input
          type="text"
          className="admin-search"
          placeholder="Search modifiers…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
      </div>

      {error && <div className="admin-error">{error}</div>}

      {/* Grouped modifier list */}
      {loading ? (
        <div className="admin-loading">Loading modifiers…</div>
      ) : filtered.length === 0 ? (
        <div className="admin-empty">
          {modifiers.length === 0
            ? 'No modifiers in this set yet.'
            : 'No modifiers match your filters.'}
        </div>
      ) : (
        <div className="admin-rarity-grid-scroll">
          <div className="admin-rarity-grid">
            {RARITIES.map((rarity) => {
              const items = grouped[rarity] ?? [];
              return (
                <div
                  key={rarity}
                  className={`admin-rarity-column ${dragOverRarity === rarity ? 'admin-rarity-column--drop' : ''}`}
                  onDragOver={(e) => {
                    e.preventDefault();
                    setDragOverRarity(rarity);
                  }}
                  onDragLeave={() => setDragOverRarity((current) => (current === rarity ? null : current))}
                  onDrop={(e) => {
                    e.preventDefault();
                    handleDropRarity(rarity);
                  }}
                >
                  <div className={`admin-rarity-column-header ${getRarityClass(rarity)}`}>
                    <span>{rarity}</span>
                    <span>{items.length}</span>
                  </div>

                  <form
                    className="admin-rarity-add-form"
                    onSubmit={(e) => handleAddModifier(rarity, e)}
                  >
                    <input
                      type="text"
                      className="admin-rarity-add-input"
                      placeholder={`Add ${rarity} modifier`}
                      value={newByRarity[rarity] ?? ''}
                      onChange={(e) =>
                        setNewByRarity((prev) => ({ ...prev, [rarity]: e.target.value }))
                      }
                    />
                    <button
                      type="submit"
                      className="admin-btn admin-btn-primary admin-btn-sm"
                      disabled={addingRarity === rarity || !(newByRarity[rarity] ?? '').trim()}
                    >
                      {addingRarity === rarity ? '…' : '+'}
                    </button>
                  </form>

                  <div className="admin-rarity-list">
                    {items.length === 0 ? (
                      <div className="admin-rarity-empty">Drop here</div>
                    ) : (
                      items.map((mod) => (
                        <div
                          key={mod.id}
                          className="admin-modifier-row"
                          draggable={editingId !== mod.id}
                          onDragStart={() => handleDragStart(mod.id)}
                          onDragEnd={handleDragEnd}
                        >
                          {editingId === mod.id ? (
                            <>
                              <input
                                className="admin-mod-col-name admin-inline-input"
                                value={editName}
                                onChange={(e) => setEditName(e.target.value)}
                                onKeyDown={(e) => {
                                  if (e.key === 'Enter') handleSaveEdit(mod.id);
                                  if (e.key === 'Escape') handleCancelEdit();
                                }}
                                autoFocus
                              />
                              <div className="admin-mod-badges">
                                <span className="admin-mini-badge">#{mod.id}</span>
                                <span className="admin-mini-badge admin-mini-badge-cards">📇 {mod.card_count}</span>
                              </div>
                              <div className="admin-mod-row-bottom">
                                <span className="admin-mod-col-actions">
                                  <button
                                    className="admin-icon-btn admin-icon-btn--save"
                                    onClick={() => handleSaveEdit(mod.id)}
                                    title="Save"
                                  >
                                    ✓
                                  </button>
                                  <button
                                    className="admin-icon-btn"
                                    onClick={handleCancelEdit}
                                    title="Cancel"
                                  >
                                    ✕
                                  </button>
                                </span>
                              </div>
                            </>
                          ) : (
                            <>
                              <span className="admin-mod-col-name">{mod.name}</span>
                              <div className="admin-mod-badges">
                                <span className="admin-mini-badge">#{mod.id}</span>
                                <span className="admin-mini-badge admin-mini-badge-cards">📇 {mod.card_count}</span>
                              </div>
                              <div className="admin-mod-row-bottom">
                                <span className="admin-mod-col-actions">
                                  <button
                                    className="admin-icon-btn admin-action-icon admin-action-icon--edit"
                                    onClick={() => handleStartEdit(mod)}
                                    title="Edit"
                                  >
                                    <EditIcon />
                                  </button>
                                  <button
                                    className="admin-icon-btn admin-action-icon admin-action-icon--delete"
                                    onClick={() => handleDelete(mod)}
                                    title="Delete"
                                  >
                                    <DeleteIcon />
                                  </button>
                                </span>
                              </div>
                            </>
                          )}
                        </div>
                      ))
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
};

export default AdminSetDetailPage;
