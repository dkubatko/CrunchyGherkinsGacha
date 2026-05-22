import { create } from 'zustand';
import { AdminApiService } from '../services/adminApi';
import type {
  AdminSet,
  AdminAspectType,
  AdminAspectByType,
} from '../types/admin';

/**
 * Shared cache for admin reference data: seasons, sets-by-season, types,
 * aspects-by-type, plus per-route scroll positions and a single source of
 * truth for the selected season.
 *
 * Pages call `ensure*` to lazily hydrate (no-op when cached) and use the
 * exposed mutators for optimistic updates. Mutators return a rollback
 * closure so callers can revert on failure.
 */

type Rollback = () => void;

interface AdminDataState {
  // ── Cached data ──
  seasons: number[] | null;
  setsBySeason: Record<number, AdminSet[] | undefined>;
  types: AdminAspectType[] | null;
  aspectsByType: Record<number, AdminAspectByType[] | undefined>;

  // ── Cross-component UI state ──
  selectedSeason: number | null;
  scrollPositions: Record<string, number>;
  expandedTypeId: number | null;

  // ── In-flight tracking (prevents duplicate fetches) ──
  loadingSeasons: boolean;
  loadingSets: Record<number, boolean>;
  loadingTypes: boolean;
  loadingAspectsForType: Record<number, boolean>;

  // ── Lazy hydration ──
  ensureSeasons: () => Promise<number[]>;
  ensureSets: (seasonId: number, force?: boolean) => Promise<AdminSet[]>;
  ensureTypes: (force?: boolean) => Promise<AdminAspectType[]>;
  ensureAspectsForType: (typeId: number, force?: boolean) => Promise<AdminAspectByType[]>;

  // ── Selection ──
  setSelectedSeason: (s: number | null) => void;

  // ── Scroll persistence ──
  setScroll: (key: string, top: number) => void;
  getScroll: (key: string) => number;

  // ── Types UI ──
  setExpandedTypeId: (id: number | null) => void;

  // ── Optimistic mutators ──
  applySetUpdate: (seasonId: number, setId: number, patch: Partial<AdminSet>) => Rollback;
  applySetReplace: (next: AdminSet) => Rollback;
  applySetRemove: (seasonId: number, setId: number) => Rollback;
  applySetInsert: (next: AdminSet) => Rollback;
  adjustSetAspectCount: (seasonId: number, setId: number, delta: number) => Rollback;

  applyTypeUpsert: (next: AdminAspectType) => Rollback;
  applyTypeRemove: (typeId: number) => Rollback;
  invalidateAspectsForType: (typeId: number) => void;

  // ── Reset (logout) ──
  resetData: () => void;
}

const SCROLL_DEFAULT = 0;

export const useAdminDataStore = create<AdminDataState>((set, get) => ({
  seasons: null,
  setsBySeason: {},
  types: null,
  aspectsByType: {},

  selectedSeason: null,
  scrollPositions: {},
  expandedTypeId: null,

  loadingSeasons: false,
  loadingSets: {},
  loadingTypes: false,
  loadingAspectsForType: {},

  ensureSeasons: async () => {
    const { seasons, loadingSeasons } = get();
    if (seasons !== null) return seasons;
    if (loadingSeasons) {
      // Wait for the in-flight request to finish.
      return new Promise<number[]>((resolve) => {
        const unsub = useAdminDataStore.subscribe((s) => {
          if (s.seasons !== null && !s.loadingSeasons) {
            unsub();
            resolve(s.seasons);
          }
        });
      });
    }
    set({ loadingSeasons: true });
    try {
      const data = await AdminApiService.getSeasons();
      set((prev) => ({
        seasons: data,
        loadingSeasons: false,
        // Default selected season to the most recent if not already set.
        selectedSeason: prev.selectedSeason ?? (data.length > 0 ? data[data.length - 1] : null),
      }));
      return data;
    } catch (err) {
      set({ loadingSeasons: false });
      throw err;
    }
  },

  ensureSets: async (seasonId, force = false) => {
    const { setsBySeason, loadingSets } = get();
    const cached = setsBySeason[seasonId];
    if (!force && cached !== undefined) return cached;
    if (loadingSets[seasonId]) {
      return new Promise<AdminSet[]>((resolve) => {
        const unsub = useAdminDataStore.subscribe((s) => {
          if (!s.loadingSets[seasonId] && s.setsBySeason[seasonId] !== undefined) {
            unsub();
            resolve(s.setsBySeason[seasonId] as AdminSet[]);
          }
        });
      });
    }
    set((prev) => ({ loadingSets: { ...prev.loadingSets, [seasonId]: true } }));
    try {
      const data = await AdminApiService.getSetsBySeason(seasonId);
      set((prev) => ({
        setsBySeason: { ...prev.setsBySeason, [seasonId]: data },
        loadingSets: { ...prev.loadingSets, [seasonId]: false },
      }));
      return data;
    } catch (err) {
      set((prev) => ({ loadingSets: { ...prev.loadingSets, [seasonId]: false } }));
      throw err;
    }
  },

  ensureTypes: async (force = false) => {
    const { types, loadingTypes } = get();
    if (!force && types !== null) return types;
    if (loadingTypes) {
      return new Promise<AdminAspectType[]>((resolve) => {
        const unsub = useAdminDataStore.subscribe((s) => {
          if (s.types !== null && !s.loadingTypes) {
            unsub();
            resolve(s.types);
          }
        });
      });
    }
    set({ loadingTypes: true });
    try {
      const data = await AdminApiService.getTypes();
      set({ types: data, loadingTypes: false });
      return data;
    } catch (err) {
      set({ loadingTypes: false });
      throw err;
    }
  },

  ensureAspectsForType: async (typeId, force = false) => {
    const { aspectsByType, loadingAspectsForType } = get();
    const cached = aspectsByType[typeId];
    if (!force && cached !== undefined) return cached;
    if (loadingAspectsForType[typeId]) {
      return new Promise<AdminAspectByType[]>((resolve) => {
        const unsub = useAdminDataStore.subscribe((s) => {
          if (!s.loadingAspectsForType[typeId] && s.aspectsByType[typeId] !== undefined) {
            unsub();
            resolve(s.aspectsByType[typeId] as AdminAspectByType[]);
          }
        });
      });
    }
    set((prev) => ({
      loadingAspectsForType: { ...prev.loadingAspectsForType, [typeId]: true },
    }));
    try {
      const data = await AdminApiService.getAspectsByType(typeId);
      set((prev) => ({
        aspectsByType: { ...prev.aspectsByType, [typeId]: data },
        loadingAspectsForType: { ...prev.loadingAspectsForType, [typeId]: false },
      }));
      return data;
    } catch (err) {
      set((prev) => ({
        loadingAspectsForType: { ...prev.loadingAspectsForType, [typeId]: false },
      }));
      throw err;
    }
  },

  setSelectedSeason: (s) => set({ selectedSeason: s }),

  setScroll: (key, top) =>
    set((prev) => ({ scrollPositions: { ...prev.scrollPositions, [key]: top } })),
  getScroll: (key) => get().scrollPositions[key] ?? SCROLL_DEFAULT,

  setExpandedTypeId: (id) => set({ expandedTypeId: id }),

  applySetUpdate: (seasonId, setId, patch) => {
    const prev = get().setsBySeason[seasonId];
    if (!prev) return () => undefined;
    const next = prev.map((s) => (s.id === setId ? { ...s, ...patch } : s));
    set((p) => ({ setsBySeason: { ...p.setsBySeason, [seasonId]: next } }));
    return () => {
      set((p) => ({ setsBySeason: { ...p.setsBySeason, [seasonId]: prev } }));
    };
  },

  applySetReplace: (nextSet) => {
    const seasonId = nextSet.season_id;
    const prev = get().setsBySeason[seasonId];
    if (!prev) {
      set((p) => ({ setsBySeason: { ...p.setsBySeason, [seasonId]: [nextSet] } }));
      return () => {
        set((p) => {
          const copy = { ...p.setsBySeason };
          delete copy[seasonId];
          return { setsBySeason: copy };
        });
      };
    }
    const exists = prev.some((s) => s.id === nextSet.id);
    const next = exists
      ? prev.map((s) => (s.id === nextSet.id ? nextSet : s))
      : [...prev, nextSet];
    set((p) => ({ setsBySeason: { ...p.setsBySeason, [seasonId]: next } }));
    return () => {
      set((p) => ({ setsBySeason: { ...p.setsBySeason, [seasonId]: prev } }));
    };
  },

  applySetRemove: (seasonId, setId) => {
    const prev = get().setsBySeason[seasonId];
    if (!prev) return () => undefined;
    const next = prev.filter((s) => s.id !== setId);
    set((p) => ({ setsBySeason: { ...p.setsBySeason, [seasonId]: next } }));
    return () => {
      set((p) => ({ setsBySeason: { ...p.setsBySeason, [seasonId]: prev } }));
    };
  },

  applySetInsert: (nextSet) => {
    const seasonId = nextSet.season_id;
    const prev = get().setsBySeason[seasonId];
    const next = prev ? [...prev, nextSet] : [nextSet];
    set((p) => ({ setsBySeason: { ...p.setsBySeason, [seasonId]: next } }));
    return () => {
      set((p) => ({
        setsBySeason: { ...p.setsBySeason, [seasonId]: prev ?? [] },
      }));
    };
  },

  adjustSetAspectCount: (seasonId, setId, delta) => {
    const prev = get().setsBySeason[seasonId];
    if (!prev) return () => undefined;
    const next = prev.map((s) =>
      s.id === setId ? { ...s, aspect_count: Math.max(0, s.aspect_count + delta) } : s,
    );
    set((p) => ({ setsBySeason: { ...p.setsBySeason, [seasonId]: next } }));
    return () => {
      set((p) => ({ setsBySeason: { ...p.setsBySeason, [seasonId]: prev } }));
    };
  },

  applyTypeUpsert: (nextType) => {
    const prev = get().types;
    if (prev === null) {
      set({ types: [nextType] });
      return () => set({ types: null });
    }
    const exists = prev.some((t) => t.id === nextType.id);
    const next = exists
      ? prev.map((t) => (t.id === nextType.id ? nextType : t))
      : [...prev, nextType];
    set({ types: next });
    return () => set({ types: prev });
  },

  applyTypeRemove: (typeId) => {
    const prev = get().types;
    if (prev === null) return () => undefined;
    const next = prev.filter((t) => t.id !== typeId);
    set((p) => {
      const aspectsCopy = { ...p.aspectsByType };
      delete aspectsCopy[typeId];
      return { types: next, aspectsByType: aspectsCopy };
    });
    return () => set({ types: prev });
  },

  invalidateAspectsForType: (typeId) => {
    set((p) => {
      const copy = { ...p.aspectsByType };
      delete copy[typeId];
      return { aspectsByType: copy };
    });
  },

  resetData: () =>
    set({
      seasons: null,
      setsBySeason: {},
      types: null,
      aspectsByType: {},
      selectedSeason: null,
      scrollPositions: {},
      expandedTypeId: null,
      loadingSeasons: false,
      loadingSets: {},
      loadingTypes: false,
      loadingAspectsForType: {},
    }),
}));
