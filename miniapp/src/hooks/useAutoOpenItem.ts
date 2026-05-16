import { useEffect, useRef } from 'react';

/**
 * Deep-link helper: once `items` includes the row whose id matches `pendingId`,
 * fire `openModal(item)` exactly once for that id. Resets when `pendingId`
 * is cleared so re-deep-linking to the same id later still works.
 */
export function useAutoOpenItem<T extends { id: number }>(
  items: T[],
  pendingId: number | null | undefined,
  openModal: (item: T) => void,
  loading: boolean,
): void {
  const firedForIdRef = useRef<number | null>(null);

  useEffect(() => {
    if (pendingId == null) {
      firedForIdRef.current = null;
      return;
    }
    if (loading) return;
    if (firedForIdRef.current === pendingId) return;
    const target = items.find((it) => it.id === pendingId);
    if (!target) return;
    firedForIdRef.current = pendingId;
    openModal(target);
  }, [pendingId, items, loading, openModal]);
}
