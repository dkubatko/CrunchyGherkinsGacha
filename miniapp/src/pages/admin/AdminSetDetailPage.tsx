import React, { useEffect, useState, useCallback, useMemo, useRef } from 'react';
import { AdminApiService } from '../../services/adminApi';
import { useAdminDataStore } from '../../stores/useAdminDataStore';
import { useAdminUnsavedGuard } from '../../hooks/useAdminUnsavedGuard';
import AdminPopover from './AdminPopover';
import type {
  AdminSet,
  AdminAspectDef,
  AdminAspectDefCreate,
  AdminAspectDefUpdate,
} from '../../types/admin';
import './Admin.css';

const RARITIES = ['Common', 'Rare', 'Epic', 'Legendary'];

const EditIcon = () => (
  <svg viewBox="0 0 24 24" aria-hidden="true" focusable="false">
    <path d="M12 20h9" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
    <path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4 12.5-12.5z" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" fill="none" />
  </svg>
);

const DeleteIcon = () => (
  <svg viewBox="0 0 24 24" aria-hidden="true" focusable="false">
    <path d="M3 6h18" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
    <path d="M8 6V4h8v2" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" fill="none" />
    <path d="M19 6l-1 14H6L5 6" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" fill="none" />
    <path d="M10 11v6M14 11v6" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" fill="none" />
  </svg>
);

const MoveIcon = () => (
  <svg viewBox="0 0 24 24" aria-hidden="true" focusable="false">
    <path d="M5 12h14M13 6l6 6-6 6" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" fill="none" />
  </svg>
);

interface Props {
  setId: number;
  seasonId: number;
  onSetDeleted?: () => void;
}
interface DraftNewAspect {
  tempId: number;
  set_id: number;
  season_id: number;
  name: string;
  rarity: string;
  type_id: number | null;
}

// Field-level draft of edits to an existing aspect.
interface DraftEdit {
  name?: string;
  rarity?: string;
  set_id?: number;
  type_id?: number | null;
}

const AdminSetDetailPage: React.FC<Props> = ({ setId, seasonId, onSetDeleted }) => {
  // ── Store-backed data ──
  const setsBySeason = useAdminDataStore((s) => s.setsBySeason);
  const types = useAdminDataStore((s) => s.types);
  const ensureSets = useAdminDataStore((s) => s.ensureSets);
  const ensureTypes = useAdminDataStore((s) => s.ensureTypes);
  const applySetReplace = useAdminDataStore((s) => s.applySetReplace);
  const applySetRemove = useAdminDataStore((s) => s.applySetRemove);
  const adjustSetAspectCount = useAdminDataStore((s) => s.adjustSetAspectCount);

  const siblingSets = setsBySeason[seasonId] ?? [];
  const set: AdminSet | undefined = siblingSets.find((s) => s.id === setId);

  // ── Hydration ──
  const [hydrating, setHydrating] = useState(set === undefined || types === null);
  const [hydrateError, setHydrateError] = useState('');

  useEffect(() => {
    let cancelled = false;
    Promise.all([ensureSets(seasonId), ensureTypes()])
      .then(() => {
        if (!cancelled) setHydrating(false);
      })
      .catch((err) => {
        if (!cancelled) {
          setHydrateError(err instanceof Error ? err.message : 'Failed to load set');
          setHydrating(false);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [seasonId, ensureSets, ensureTypes]);

  // ── Aspect defs (local; not in store because high-churn) ──
  const [originalDefs, setOriginalDefs] = useState<AdminAspectDef[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  // ── Staged edits ──
  const [draftEdits, setDraftEdits] = useState<Record<number, DraftEdit>>({});
  const [deletedIds, setDeletedIds] = useState<Set<number>>(new Set());
  const [newDefs, setNewDefs] = useState<DraftNewAspect[]>([]);

  // ── UI ──
  const [search, setSearch] = useState('');
  const [filterTypeId, setFilterTypeId] = useState<number | 'none' | null>(null);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [editName, setEditName] = useState('');
  const [openTypeForId, setOpenTypeForId] = useState<number | null>(null);
  const [openMoveForId, setOpenMoveForId] = useState<number | null>(null);
  const [typeAnchor, setTypeAnchor] = useState<HTMLElement | null>(null);
  const [moveAnchor, setMoveAnchor] = useState<HTMLElement | null>(null);

  const [newByRarity, setNewByRarity] = useState<Record<string, string>>({
    Common: '', Rare: '', Epic: '', Legendary: '',
  });

  // ── Description / icon ──
  const [editingDescription, setEditingDescription] = useState(false);
  const [descriptionDraft, setDescriptionDraft] = useState(set?.description ?? '');
  const [savingDescription, setSavingDescription] = useState(false);
  const [regeneratingIcon, setRegeneratingIcon] = useState(false);
  const [showIconPreview, setShowIconPreview] = useState(false);

  // ── DnD ──
  const [draggedId, setDraggedId] = useState<number | null>(null);
  const [dragOverRarity, setDragOverRarity] = useState<string | null>(null);

  const [saving, setSaving] = useState(false);
  const [deletingSet, setDeletingSet] = useState(false);

  const tempIdCounter = useRef(-1);

  const loadAspectDefs = useCallback(async (silent = false) => {
    if (!silent) setLoading(true);
    setError('');
    try {
      const data = await AdminApiService.getAspectDefs(setId, seasonId);
      setOriginalDefs(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load aspects');
    } finally {
      setLoading(false);
    }
  }, [setId, seasonId]);

  useEffect(() => {
    loadAspectDefs();
  }, [loadAspectDefs]);

  // Reset stage on set switch.
  useEffect(() => {
    setDraftEdits({});
    setDeletedIds(new Set());
    setNewDefs([]);
    setEditingId(null);
    setOpenTypeForId(null);
    setOpenMoveForId(null);
    setTypeAnchor(null);
    setMoveAnchor(null);
  }, [setId]);

  // Sync description draft when the store's set changes.
  useEffect(() => {
    setDescriptionDraft(set?.description ?? '');
  }, [set?.description]);

  // ── Derived rows / filtering / grouping ──
  type EffectiveRow =
    | { kind: 'existing'; id: number; original: AdminAspectDef; effective: { name: string; rarity: string; set_id: number; type_id: number | null }; isDirty: boolean; isMoved: boolean; isDeleted: boolean; }
    | { kind: 'new'; id: number; draft: DraftNewAspect };

  const rows = useMemo<EffectiveRow[]>(() => {
    const existing: EffectiveRow[] = originalDefs.map((d) => {
      const draft = draftEdits[d.id] ?? {};
      const effective = {
        name: draft.name ?? d.name,
        rarity: draft.rarity ?? d.rarity,
        set_id: draft.set_id ?? d.set_id,
        type_id: draft.type_id !== undefined ? draft.type_id : (d.type_id ?? null),
      };
      const isDirty =
        (draft.name !== undefined && draft.name !== d.name) ||
        (draft.rarity !== undefined && draft.rarity !== d.rarity) ||
        (draft.set_id !== undefined && draft.set_id !== d.set_id) ||
        (draft.type_id !== undefined && draft.type_id !== (d.type_id ?? null));
      return {
        kind: 'existing' as const,
        id: d.id,
        original: d,
        effective,
        isDirty,
        isMoved: effective.set_id !== d.set_id,
        isDeleted: deletedIds.has(d.id),
      };
    });
    const news: EffectiveRow[] = newDefs.map((n) => ({ kind: 'new' as const, id: n.tempId, draft: n }));
    return [...existing, ...news];
  }, [originalDefs, draftEdits, deletedIds, newDefs]);

  const visibleRows = useMemo(() => {
    return rows.filter((r) => {
      const name = r.kind === 'existing' ? r.effective.name : r.draft.name;
      const typeId = r.kind === 'existing' ? r.effective.type_id : r.draft.type_id;
      if (search && !name.toLowerCase().includes(search.toLowerCase())) return false;
      if (filterTypeId !== null) {
        if (filterTypeId === 'none') {
          if (typeId != null) return false;
        } else {
          if (typeId !== filterTypeId) return false;
        }
      }
      return true;
    });
  }, [rows, search, filterTypeId]);

  const grouped = useMemo(() => {
    const out: Record<string, EffectiveRow[]> = { Common: [], Rare: [], Epic: [], Legendary: [] };
    for (const r of visibleRows) {
      const rarity = r.kind === 'existing' ? r.effective.rarity : r.draft.rarity;
      if (out[rarity]) out[rarity].push(r);
    }
    for (const r of RARITIES) {
      out[r].sort((a, b) => {
        const an = a.kind === 'existing' ? a.effective.name : a.draft.name;
        const bn = b.kind === 'existing' ? b.effective.name : b.draft.name;
        return an.localeCompare(bn, undefined, { sensitivity: 'base' });
      });
    }
    return out;
  }, [visibleRows]);

  // ── Stage mutators ──
  const stageEdit = (id: number, patch: DraftEdit) => {
    setDraftEdits((prev) => {
      const merged = { ...(prev[id] ?? {}), ...patch };
      const orig = originalDefs.find((d) => d.id === id);
      if (orig) {
        if (merged.name !== undefined && merged.name === orig.name) delete merged.name;
        if (merged.rarity !== undefined && merged.rarity === orig.rarity) delete merged.rarity;
        if (merged.set_id !== undefined && merged.set_id === orig.set_id) delete merged.set_id;
        if (merged.type_id !== undefined && merged.type_id === (orig.type_id ?? null)) delete merged.type_id;
      }
      const next = { ...prev };
      if (Object.keys(merged).length === 0) delete next[id];
      else next[id] = merged;
      return next;
    });
  };

  const stageNewType = (tempId: number, type_id: number | null) => {
    setNewDefs((prev) => prev.map((n) => (n.tempId === tempId ? { ...n, type_id } : n)));
  };

  const stageNewRarity = (tempId: number, rarity: string) => {
    setNewDefs((prev) => prev.map((n) => (n.tempId === tempId ? { ...n, rarity } : n)));
  };

  const stageDelete = (id: number) => {
    if (id < 0) {
      setNewDefs((prev) => prev.filter((n) => n.tempId !== id));
    } else {
      setDeletedIds((prev) => {
        const next = new Set(prev);
        if (next.has(id)) next.delete(id);
        else next.add(id);
        return next;
      });
      setEditingId((cur) => (cur === id ? null : cur));
    }
  };

  const handleAddAspect = (rarity: string, e: React.FormEvent) => {
    e.preventDefault();
    const name = (newByRarity[rarity] ?? '').trim();
    if (!name || !set) return;
    const tempId = tempIdCounter.current--;
    setNewDefs((prev) => [
      ...prev,
      {
        tempId,
        set_id: set.id,
        season_id: set.season_id,
        name,
        rarity,
        type_id: null,
      },
    ]);
    setNewByRarity((prev) => ({ ...prev, [rarity]: '' }));
  };

  const dirty = Object.keys(draftEdits).length > 0 || deletedIds.size > 0 || newDefs.length > 0;
  const counts = {
    edits: Object.keys(draftEdits).length,
    deletes: deletedIds.size,
    creates: newDefs.length,
  };

  // Warn before navigating away with unsaved changes.
  useAdminUnsavedGuard(dirty);

  const handleCancelAll = () => {
    setDraftEdits({});
    setDeletedIds(new Set());
    setNewDefs([]);
    setEditingId(null);
    setOpenTypeForId(null);
    setOpenMoveForId(null);
    setTypeAnchor(null);
    setMoveAnchor(null);
  };

  // ── Parallelized save ──
  const handleSaveAll = async () => {
    if (!dirty || !set) return;
    setSaving(true);
    setError('');
    let succeeded = 0;
    let failed = 0;

    // Snapshot net aspect count change so we can bump the set card.
    const createdCount = newDefs.length;
    const deletedCount = deletedIds.size;

    try {
      // Run deletes and updates concurrently. Group operations by kind to keep failure aggregation tidy.
      const deletePromises = Array.from(deletedIds).map((id) =>
        AdminApiService.deleteAspectDef(id),
      );

      const updatePromises = Object.entries(draftEdits)
        .filter(([idStr]) => !deletedIds.has(Number(idStr)))
        .map(([idStr, draft]) => {
          const id = Number(idStr);
          const payload: AdminAspectDefUpdate = {};
          if (draft.name !== undefined) payload.name = draft.name;
          if (draft.rarity !== undefined) payload.rarity = draft.rarity;
          if (draft.set_id !== undefined) payload.set_id = draft.set_id;
          if (draft.type_id !== undefined) {
            payload.type_id = draft.type_id === null ? 0 : draft.type_id;
          }
          return AdminApiService.updateAspectDef(id, payload);
        });

      // Creates: try /bulk first (no type_id support there). Fall back to per-item if any new def carries a type_id.
      let createPromises: Promise<unknown>[] = [];
      const bulkEligible = newDefs.filter((n) => n.type_id == null);
      const perItemNeeded = newDefs.filter((n) => n.type_id != null);
      if (bulkEligible.length > 0) {
        createPromises.push(
          AdminApiService.bulkUpsertAspectDefs(
            seasonId,
            bulkEligible.map((n) => ({
              set_id: n.set_id,
              season_id: n.season_id,
              name: n.name,
              rarity: n.rarity,
            })),
          ),
        );
      }
      for (const n of perItemNeeded) {
        const payload: AdminAspectDefCreate = {
          set_id: n.set_id,
          season_id: n.season_id,
          name: n.name,
          rarity: n.rarity,
          type_id: n.type_id ?? undefined,
        };
        createPromises.push(AdminApiService.createAspectDef(payload));
      }

      const [delResults, updResults, crResults] = await Promise.all([
        Promise.allSettled(deletePromises),
        Promise.allSettled(updatePromises),
        Promise.allSettled(createPromises),
      ]);

      for (const r of delResults) r.status === 'fulfilled' ? succeeded++ : failed++;
      for (const r of updResults) r.status === 'fulfilled' ? succeeded++ : failed++;
      for (const r of crResults) {
        if (r.status === 'fulfilled') {
          // Bulk endpoint returns a count; per-item returns one def. Either way: success.
          succeeded++;
        } else {
          failed++;
        }
      }

      // Reload aspect defs (single fetch — covers all created/updated/deleted state).
      await loadAspectDefs(true);
      handleCancelAll();

      // Optimistically adjust the set's aspect_count in the store.
      const delta = createdCount - deletedCount;
      if (delta !== 0) adjustSetAspectCount(seasonId, setId, delta);

      if (failed > 0) {
        setError(`${succeeded} change(s) saved, ${failed} failed.`);
      }
    } finally {
      setSaving(false);
    }
  };

  // ── Set-level mutations ──
  const handleSaveDescription = async () => {
    if (!set) return;
    const nextDescription = descriptionDraft.trim();
    if (nextDescription === (set.description ?? '').trim()) {
      setEditingDescription(false);
      return;
    }
    setSavingDescription(true);
    setError('');
    try {
      const updated = await AdminApiService.updateSet(set.season_id, set.id, { description: nextDescription });
      applySetReplace(updated);
      setEditingDescription(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to update description');
    } finally {
      setSavingDescription(false);
    }
  };

  const handleRegenerateIcon = async () => {
    if (!set) return;
    setRegeneratingIcon(true);
    setError('');
    try {
      const updated = await AdminApiService.regenerateSetIcon(set.season_id, set.id);
      applySetReplace(updated);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to regenerate icon');
    } finally {
      setRegeneratingIcon(false);
    }
  };

  const handleDeleteSet = async () => {
    if (!set) return;
    if (!window.confirm(`Delete set "${set.name}"? This cannot be undone.`)) return;
    setDeletingSet(true);
    setError('');
    try {
      await AdminApiService.deleteSet(set.season_id, set.id);
      applySetRemove(set.season_id, set.id);
      onSetDeleted?.();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to delete set');
      setDeletingSet(false);
    }
  };

  // ── DnD ──
  const handleDragStart = (id: number) => setDraggedId(id);
  const handleDragEnd = () => { setDraggedId(null); setDragOverRarity(null); };
  const handleDropRarity = (targetRarity: string) => {
    if (draggedId == null) { handleDragEnd(); return; }
    if (draggedId < 0) {
      stageNewRarity(draggedId, targetRarity);
    } else {
      const orig = originalDefs.find((d) => d.id === draggedId);
      const currentRarity = (draftEdits[draggedId]?.rarity ?? orig?.rarity);
      if (currentRarity !== targetRarity) {
        stageEdit(draggedId, { rarity: targetRarity });
      }
    }
    handleDragEnd();
  };

  const getRarityClass = (rarity: string) => `rarity-${rarity.toLowerCase()}`;

  const typeName = (id: number | null) => {
    if (id == null) return null;
    return (types ?? []).find((t) => t.id === id)?.name ?? null;
  };

  useEffect(() => {
    if (editingId != null && deletedIds.has(editingId)) {
      setEditingId(null);
    }
  }, [deletedIds, editingId]);

  // ── Early returns ──
  if (hydrating) {
    return (
      <div className="admin-content">
        <div className="admin-loading">Loading set…</div>
      </div>
    );
  }

  if (!set) {
    return (
      <div className="admin-content">
        <div className="admin-error">
          {hydrateError || 'Set not found.'}
        </div>
      </div>
    );
  }

  return (
    <div className="admin-content">
      <div className="admin-set-hero">
        <div className="admin-set-hero-top">
          <div className="admin-set-hero-icon-wrapper">
            {set.slot_icon_b64 ? (
              <img
                className="admin-set-hero-icon"
                src={`data:image/jpeg;base64,${set.slot_icon_b64}`}
                alt={set.name}
                onClick={() => setShowIconPreview(true)}
              />
            ) : (
              <div className="admin-set-hero-icon admin-set-hero-icon--placeholder" />
            )}
            <button
              className="admin-btn admin-btn-secondary admin-btn-sm admin-set-hero-regen"
              onClick={handleRegenerateIcon}
              disabled={regeneratingIcon}
              title="Regenerate slot icon"
            >
              {regeneratingIcon ? (
                <span className="admin-set-hero-regen-spinner" aria-label="Regenerating" />
              ) : (
                <span className="admin-set-hero-regen-icon">↻</span>
              )}
            </button>
          </div>
          <div className="admin-set-hero-info">
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
              <span>
                {loading && originalDefs.length === 0 && newDefs.length === 0 && deletedIds.size === 0
                  ? set.aspect_count
                  : originalDefs.length - deletedIds.size + newDefs.length}{' '}
                aspects
              </span>
              <span className="admin-set-meta-sep">·</span>
              <span>{set.source}</span>
            </div>
            {!loading && originalDefs.length === 0 && newDefs.length === 0 && onSetDeleted && (
              <button
                className="admin-btn admin-btn-danger admin-btn-sm admin-set-delete-btn"
                onClick={handleDeleteSet}
                disabled={deletingSet}
                title="Delete this empty set"
              >
                {deletingSet ? 'Deleting…' : 'Delete empty set'}
              </button>
            )}
          </div>
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
                  onClick={() => { setDescriptionDraft(set.description ?? ''); setEditingDescription(false); }}
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

      <div className="admin-toolbar admin-toolbar--wrap">
        <input
          type="text"
          className="admin-search"
          placeholder="Search aspects…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
      </div>

      {types && types.length > 0 && (
        <div className="admin-filter-row">
          <span className="admin-filter-label">Filter:</span>
          <button
            className={`admin-filter-chip ${filterTypeId === null ? 'admin-filter-chip--active' : ''}`}
            onClick={() => setFilterTypeId(null)}
          >
            All
          </button>
          <button
            className={`admin-filter-chip ${filterTypeId === 'none' ? 'admin-filter-chip--active' : ''}`}
            onClick={() => setFilterTypeId('none')}
          >
            (no type)
          </button>
          {types.map((t) => (
            <button
              key={t.id}
              className={`admin-filter-chip ${filterTypeId === t.id ? 'admin-filter-chip--active' : ''}`}
              onClick={() => setFilterTypeId(t.id)}
            >
              {t.name}
            </button>
          ))}
        </div>
      )}
      {error && <div className="admin-error">{error}</div>}

      {loading ? (
        <div className="admin-loading">Loading aspects…</div>
      ) : (
        <div className="admin-rarity-grid-scroll">
          <div className="admin-rarity-grid">
            {RARITIES.map((rarity) => {
              const items = grouped[rarity] ?? [];
              return (
                <div
                  key={rarity}
                  className={`admin-rarity-column ${dragOverRarity === rarity ? 'admin-rarity-column--drop' : ''}`}
                  onDragOver={(e) => { e.preventDefault(); setDragOverRarity(rarity); }}
                  onDragLeave={() => setDragOverRarity((c) => (c === rarity ? null : c))}
                  onDrop={(e) => { e.preventDefault(); handleDropRarity(rarity); }}
                >
                  <div className={`admin-rarity-column-header ${getRarityClass(rarity)}`}>
                    <span>{rarity}</span>
                    <span>{items.length}</span>
                  </div>

                  <form className="admin-rarity-add-form" onSubmit={(e) => handleAddAspect(rarity, e)}>
                    <input
                      type="text"
                      className="admin-rarity-add-input"
                      placeholder={`Add ${rarity} aspect`}
                      value={newByRarity[rarity] ?? ''}
                      onChange={(e) => setNewByRarity((prev) => ({ ...prev, [rarity]: e.target.value }))}
                    />
                    <button
                      type="submit"
                      className="admin-btn admin-btn-primary admin-btn-sm"
                      disabled={!(newByRarity[rarity] ?? '').trim()}
                      title={`Stage a new ${rarity} aspect`}
                    >
                      +
                    </button>
                  </form>

                  <div className="admin-rarity-list">
                    {items.length === 0 ? (
                      <div className="admin-rarity-empty">Drop here</div>
                    ) : (
                      items.map((row) => {
                        const id = row.id;
                        const isExisting = row.kind === 'existing';
                        const name = isExisting ? row.effective.name : row.draft.name;
                        const tId = isExisting ? row.effective.type_id : row.draft.type_id;
                        const isMoved = isExisting && row.isMoved;
                        const isDeleted = isExisting && row.isDeleted;
                        const isDirty = isExisting && row.isDirty;
                        const isNew = !isExisting;
                        const ownedCount = isExisting ? row.original.owned_count : 0;
                        const inlineEditing = editingId === id;

                        const rowClasses = [
                          'admin-aspect-row',
                          isDeleted ? 'admin-aspect-row--deleted' : '',
                          !isDeleted && isNew ? 'admin-aspect-row--new' : '',
                          !isDeleted && isMoved ? 'admin-aspect-row--moved' : '',
                          !isDeleted && isDirty && !isMoved ? 'admin-aspect-row--dirty' : '',
                        ].filter(Boolean).join(' ');

                        return (
                          <div
                            key={id}
                            className={rowClasses}
                            draggable={!inlineEditing && !isDeleted}
                            onDragStart={() => handleDragStart(id)}
                            onDragEnd={handleDragEnd}
                          >
                            {inlineEditing ? (
                              <input
                                className="admin-mod-col-name admin-inline-input"
                                value={editName}
                                onChange={(e) => setEditName(e.target.value)}
                                onKeyDown={(e) => {
                                  if (e.key === 'Enter') {
                                    if (isExisting) stageEdit(id, { name: editName.trim() });
                                    else setNewDefs((prev) => prev.map((n) => (n.tempId === id ? { ...n, name: editName.trim() } : n)));
                                    setEditingId(null);
                                  }
                                  if (e.key === 'Escape') setEditingId(null);
                                }}
                                onBlur={() => {
                                  if (editName.trim()) {
                                    if (isExisting) stageEdit(id, { name: editName.trim() });
                                    else setNewDefs((prev) => prev.map((n) => (n.tempId === id ? { ...n, name: editName.trim() } : n)));
                                  }
                                  setEditingId(null);
                                }}
                                autoFocus
                              />
                            ) : (
                              <span
                                className="admin-mod-col-name"
                                onClick={() => { if (!isDeleted) { setEditingId(id); setEditName(name); } }}
                                title={isDeleted ? 'Staged for delete' : 'Click to rename'}
                              >
                                {name}
                              </span>
                            )}

                            <div className="admin-mod-badges">
                              {isExisting && <span className="admin-mini-badge">#{id}</span>}
                              {isExisting && (
                                <span className="admin-mini-badge admin-mini-badge-cards">📇 {ownedCount}</span>
                              )}
                              <button
                                className={`admin-type-chip-inline ${tId == null ? 'admin-type-chip-inline--empty' : ''}`}
                                onClick={(e) => {
                                  if (isDeleted) return;
                                  if (openTypeForId === id) {
                                    setOpenTypeForId(null);
                                    setTypeAnchor(null);
                                  } else {
                                    setOpenTypeForId(id);
                                    setTypeAnchor(e.currentTarget);
                                    setOpenMoveForId(null);
                                    setMoveAnchor(null);
                                  }
                                }}
                                title="Set type"
                                disabled={isDeleted}
                              >
                                {tId == null ? '+ type' : (typeName(tId) ?? '?')}
                              </button>
                            </div>

                            <div className="admin-mod-row-bottom">
                              <span className="admin-mod-col-actions">
                                {isExisting && !isDeleted && (
                                  <button
                                    className="admin-icon-btn admin-action-icon admin-action-icon--move"
                                    onClick={(e) => {
                                      if (openMoveForId === id) {
                                        setOpenMoveForId(null);
                                        setMoveAnchor(null);
                                      } else {
                                        setOpenMoveForId(id);
                                        setMoveAnchor(e.currentTarget);
                                        setOpenTypeForId(null);
                                        setTypeAnchor(null);
                                      }
                                    }}
                                    title="Move to set"
                                  >
                                    <MoveIcon />
                                  </button>
                                )}
                                {!isDeleted && (
                                  <button
                                    className="admin-icon-btn admin-action-icon admin-action-icon--edit"
                                    onClick={() => { setEditingId(id); setEditName(name); }}
                                    title="Rename"
                                  >
                                    <EditIcon />
                                  </button>
                                )}
                                <button
                                  className="admin-icon-btn admin-action-icon admin-action-icon--delete"
                                  onClick={() => stageDelete(id)}
                                  title={isDeleted ? 'Undo delete' : (isNew ? 'Discard' : 'Stage delete')}
                                >
                                  <DeleteIcon />
                                </button>
                              </span>
                            </div>
                          </div>
                        );
                      })
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {showIconPreview && set.slot_icon_b64 && (
        <div className="icon-preview-overlay" onClick={() => setShowIconPreview(false)}>
          <img
            className="icon-preview-image"
            src={`data:image/jpeg;base64,${set.slot_icon_b64}`}
            alt={set.name}
          />
        </div>
      )}

      {openTypeForId != null && typeAnchor && (() => {
        const row = rows.find((r) => r.id === openTypeForId);
        if (!row) return null;
        const isExisting = row.kind === 'existing';
        const curType = isExisting ? row.effective.type_id : row.draft.type_id;
        const rowId = row.id;
        const close = () => { setOpenTypeForId(null); setTypeAnchor(null); };
        return (
          <AdminPopover anchor={typeAnchor} onClose={close} className="admin-popover--type">
            <button
              className={`admin-popover-item ${curType == null ? 'admin-popover-item--selected' : ''}`}
              onClick={() => {
                if (isExisting) stageEdit(rowId, { type_id: null });
                else stageNewType(rowId, null);
                close();
              }}
            >
              None
            </button>
            {(types ?? []).map((t) => (
              <button
                key={t.id}
                className={`admin-popover-item ${curType === t.id ? 'admin-popover-item--selected' : ''}`}
                onClick={() => {
                  if (isExisting) stageEdit(rowId, { type_id: t.id });
                  else stageNewType(rowId, t.id);
                  close();
                }}
              >
                {t.name}
              </button>
            ))}
          </AdminPopover>
        );
      })()}

      {openMoveForId != null && moveAnchor && (() => {
        const row = rows.find((r) => r.id === openMoveForId);
        if (!row || row.kind !== 'existing') return null;
        const curSetId = row.effective.set_id;
        const rowId = row.id;
        const close = () => { setOpenMoveForId(null); setMoveAnchor(null); };
        return (
          <AdminPopover anchor={moveAnchor} onClose={close} className="admin-popover--move">
            {siblingSets.length === 0 ? (
              <div className="admin-popover-empty">No other sets</div>
            ) : (
              siblingSets.map((s) => (
                <button
                  key={s.id}
                  className={`admin-popover-item ${s.id === curSetId ? 'admin-popover-item--selected' : ''}`}
                  onClick={() => {
                    stageEdit(rowId, { set_id: s.id });
                    close();
                  }}
                >
                  {s.name}
                </button>
              ))
            )}
          </AdminPopover>
        );
      })()}

      {dirty && (
        <div className="admin-save-bar">
          <div className="admin-save-bar-summary">
            {counts.edits > 0 && <span>{counts.edits} edit{counts.edits === 1 ? '' : 's'}</span>}
            {counts.creates > 0 && <span>{counts.creates} new</span>}
            {counts.deletes > 0 && <span>{counts.deletes} removed</span>}
          </div>
          <div className="admin-save-bar-actions">
            <button
              className="admin-btn admin-btn-secondary admin-btn-sm"
              onClick={handleCancelAll}
              disabled={saving}
            >
              Cancel
            </button>
            <button
              className="admin-btn admin-btn-primary admin-btn-sm"
              onClick={handleSaveAll}
              disabled={saving}
            >
              {saving ? 'Saving…' : 'Save changes'}
            </button>
          </div>
        </div>
      )}
    </div>
  );
};

export default AdminSetDetailPage;
