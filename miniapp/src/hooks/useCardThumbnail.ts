/**
 * Card thumbnail fetching and caching.
 *
 * Provides both an imperative `prefetchThumbnail()` for pre-loading images
 * before animations start, and a React hook `useCardThumbnail()` for
 * reactive rendering in card components.
 *
 * All functions share one module-level cache so a thumbnail fetched via
 * `prefetchThumbnail()` is instantly available to `useCardThumbnail()`.
 */

import { useState, useEffect, useRef } from 'react';
import { ApiService } from '@/services/api';

// ── Shared module-level state ───────────────────────────────────────────────

/** card_id → base64 thumbnail */
const cache = new Map<number, string>();

/** card_id → in-flight promise (deduplicates concurrent requests) */
const inflight = new Map<number, Promise<string>>();

// ── Imperative API ──────────────────────────────────────────────────────────

/**
 * Fetch a card thumbnail and store it in the shared cache.
 * Returns the base64 string. If the thumbnail is already cached or a
 * request is in-flight, the existing value / promise is reused.
 *
 * Use this to pre-load a thumbnail *before* starting an animation so the
 * image is ready the instant the card face is revealed.
 */
export async function prefetchThumbnail(
  cardId: number,
  initData: string,
): Promise<string> {
  const cached = cache.get(cardId);
  if (cached) return cached;

  let promise = inflight.get(cardId);
  if (!promise) {
    promise = ApiService.fetchCardThumbnail(cardId, initData);
    inflight.set(cardId, promise);
  }

  try {
    const b64 = await promise;
    cache.set(cardId, b64);
    return b64;
  } finally {
    inflight.delete(cardId);
  }
}

/**
 * Clear the thumbnail cache. Call when starting a new game.
 */
export function clearThumbnailCache(): void {
  cache.clear();
}

// ── React hook ──────────────────────────────────────────────────────────────

interface UseCardThumbnailResult {
  thumbnail: string | null;
  loading: boolean;
}

/**
 * Reactively fetch & cache a card's thumbnail.
 *
 * @param cardId  Card to fetch (pass `null` to skip).
 * @param initData  Telegram auth token.
 */
export function useCardThumbnail(
  cardId: number | null,
  initData: string,
): UseCardThumbnailResult {
  const [thumbnail, setThumbnail] = useState<string | null>(
    cardId !== null ? (cache.get(cardId) ?? null) : null,
  );
  const [loading, setLoading] = useState(false);
  const mountedRef = useRef(true);

  useEffect(() => {
    mountedRef.current = true;
    return () => { mountedRef.current = false; };
  }, []);

  useEffect(() => {
    if (cardId === null) {
      setThumbnail(null);
      setLoading(false);
      return;
    }

    // Already in cache (e.g. pre-fetched before animation)
    const cached = cache.get(cardId);
    if (cached) {
      setThumbnail(cached);
      setLoading(false);
      return;
    }

    let cancelled = false;
    setLoading(true);

    prefetchThumbnail(cardId, initData)
      .then((b64) => {
        if (!cancelled && mountedRef.current) {
          setThumbnail(b64);
          setLoading(false);
        }
      })
      .catch(() => {
        if (!cancelled && mountedRef.current) {
          setLoading(false);
        }
      });

    return () => { cancelled = true; };
  }, [cardId, initData]);

  return { thumbnail, loading };
}
