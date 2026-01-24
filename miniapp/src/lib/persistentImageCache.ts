/**
 * Persistent IndexedDB-backed image cache with LRU eviction.
 * 
 * Features:
 * - Persistent storage across sessions via IndexedDB
 * - LRU eviction with thumbnail priority (full images evicted first)
 * - Cache validation via image_updated_at timestamp
 * - Graceful fallback if IndexedDB unavailable
 */

export type ImageVariant = 'full' | 'thumb';

export interface CacheEntry {
  cardId: number;
  variant: ImageVariant;
  data: string;  // base64 image data
  imageUpdatedAt: string | null;  // server timestamp for cache validation
  cachedAt: number;  // when we cached it (fallback TTL)
  lastAccessedAt: number;  // for LRU eviction
  size: number;  // approximate size in bytes for quota management
}

// Compound key for cache entries
type CacheKey = `${ImageVariant}:${number}`;

const DB_NAME = 'cardImageCache';
const DB_VERSION = 1;
const STORE_NAME = 'images';

// Cache limits - conservative for mobile WebViews
// Average thumbnail ~50KB, average full image ~500KB
const MAX_CACHE_SIZE_BYTES = 30 * 1024 * 1024;  // 30MB total
const THUMBNAIL_RESERVE_BYTES = 10 * 1024 * 1024;  // Reserve 10MB for thumbnails

class PersistentImageCache {
  private db: IDBDatabase | null = null;
  private dbReady: Promise<boolean>;
  private isAvailable = true;
  
  // In-memory index for fast lookups without hitting IndexedDB
  private memoryIndex = new Map<CacheKey, { imageUpdatedAt: string | null; lastAccessedAt: number; size: number }>();
  private totalSize = 0;

  constructor() {
    this.dbReady = this.initDB();
  }

  private async initDB(): Promise<boolean> {
    if (typeof indexedDB === 'undefined') {
      console.warn('IndexedDB not available, falling back to memory-only cache');
      this.isAvailable = false;
      return false;
    }

    return new Promise((resolve) => {
      try {
        const request = indexedDB.open(DB_NAME, DB_VERSION);

        request.onerror = () => {
          console.warn('IndexedDB open failed, falling back to memory-only cache');
          this.isAvailable = false;
          resolve(false);
        };

        request.onsuccess = () => {
          this.db = request.result;
          
          // Handle connection errors
          this.db.onerror = (event) => {
            console.error('IndexedDB error:', event);
          };

          // Build memory index from existing entries
          this.buildMemoryIndex().then(() => {
            resolve(true);
          }).catch(() => {
            resolve(true);  // DB is open, just index failed
          });
        };

        request.onupgradeneeded = (event) => {
          const db = (event.target as IDBOpenDBRequest).result;
          
          if (!db.objectStoreNames.contains(STORE_NAME)) {
            const store = db.createObjectStore(STORE_NAME, { keyPath: ['variant', 'cardId'] });
            store.createIndex('lastAccessedAt', 'lastAccessedAt', { unique: false });
            store.createIndex('variant', 'variant', { unique: false });
          }
        };

        // Timeout fallback for slow/blocked IndexedDB
        setTimeout(() => {
          if (!this.db) {
            console.warn('IndexedDB initialization timeout, falling back to memory-only cache');
            this.isAvailable = false;
            resolve(false);
          }
        }, 3000);
      } catch (err) {
        console.warn('IndexedDB init error:', err);
        this.isAvailable = false;
        resolve(false);
      }
    });
  }

  private async buildMemoryIndex(): Promise<void> {
    if (!this.db) return;

    return new Promise((resolve, reject) => {
      try {
        const transaction = this.db!.transaction(STORE_NAME, 'readonly');
        const store = transaction.objectStore(STORE_NAME);
        const request = store.openCursor();

        this.memoryIndex.clear();
        this.totalSize = 0;

        request.onsuccess = (event) => {
          const cursor = (event.target as IDBRequest<IDBCursorWithValue>).result;
          if (cursor) {
            const entry = cursor.value as CacheEntry;
            const key: CacheKey = `${entry.variant}:${entry.cardId}`;
            this.memoryIndex.set(key, {
              imageUpdatedAt: entry.imageUpdatedAt,
              lastAccessedAt: entry.lastAccessedAt,
              size: entry.size,
            });
            this.totalSize += entry.size;
            cursor.continue();
          } else {
            resolve();
          }
        };

        request.onerror = () => reject(request.error);
      } catch (err) {
        reject(err);
      }
    });
  }

  /**
   * Check if a cached image is valid (not stale) compared to server timestamp.
   * Synchronous check against memory index - may return false if index not built yet.
   */
  isValid(cardId: number, variant: ImageVariant, serverImageUpdatedAt: string | null): boolean {
    const key: CacheKey = `${variant}:${cardId}`;
    const indexEntry = this.memoryIndex.get(key);
    
    if (!indexEntry) {
      return false;
    }

    // If server has no timestamp and we have the image, it's valid
    if (!serverImageUpdatedAt) {
      return true;
    }

    // If we have no cached timestamp, assume stale
    if (!indexEntry.imageUpdatedAt) {
      return false;
    }

    // Compare timestamps - server timestamp is newer means cache is stale
    return new Date(indexEntry.imageUpdatedAt) >= new Date(serverImageUpdatedAt);
  }

  /**
   * Async version that waits for DB to be ready before checking validity.
   * Use this when you need a definitive answer about cache validity.
   */
  async isValidAsync(cardId: number, variant: ImageVariant, serverImageUpdatedAt: string | null): Promise<boolean> {
    await this.dbReady;
    return this.isValid(cardId, variant, serverImageUpdatedAt);
  }

  /**
   * Get a cached image. Returns null if not found or unavailable.
   * Updates lastAccessedAt for LRU tracking.
   * Awaits DB ready before accessing.
   */
  async get(cardId: number, variant: ImageVariant): Promise<string | null> {
    await this.dbReady;
    
    if (!this.db || !this.isAvailable) {
      return null;
    }

    const key: CacheKey = `${variant}:${cardId}`;
    if (!this.memoryIndex.has(key)) {
      return null;
    }

    return new Promise((resolve) => {
      try {
        const transaction = this.db!.transaction(STORE_NAME, 'readwrite');
        const store = transaction.objectStore(STORE_NAME);
        const request = store.get([variant, cardId]);

        request.onsuccess = () => {
          const entry = request.result as CacheEntry | undefined;
          if (!entry) {
            // Entry missing from DB but in index - clean up index
            this.memoryIndex.delete(key);
            resolve(null);
            return;
          }

          // Update lastAccessedAt for LRU
          const now = Date.now();
          entry.lastAccessedAt = now;
          store.put(entry);

          // Update memory index
          const indexEntry = this.memoryIndex.get(key);
          if (indexEntry) {
            indexEntry.lastAccessedAt = now;
          }

          resolve(entry.data);
        };

        request.onerror = () => {
          console.error('IndexedDB get error:', request.error);
          resolve(null);
        };
      } catch (err) {
        console.error('IndexedDB get exception:', err);
        resolve(null);
      }
    });
  }

  /**
   * Store an image in cache. Triggers LRU eviction if needed.
   */
  async set(
    cardId: number,
    variant: ImageVariant,
    data: string,
    imageUpdatedAt: string | null
  ): Promise<void> {
    await this.dbReady;
    
    if (!this.db || !this.isAvailable) {
      return;
    }

    const now = Date.now();
    const size = data.length;  // Approximate size in bytes
    const key: CacheKey = `${variant}:${cardId}`;

    // Check if we need to evict entries
    const existingEntry = this.memoryIndex.get(key);
    const sizeIncrease = existingEntry ? size - existingEntry.size : size;
    
    if (this.totalSize + sizeIncrease > MAX_CACHE_SIZE_BYTES) {
      await this.evictEntries(sizeIncrease);
    }

    const entry: CacheEntry = {
      cardId,
      variant,
      data,
      imageUpdatedAt,
      cachedAt: now,
      lastAccessedAt: now,
      size,
    };

    return new Promise((resolve) => {
      try {
        const transaction = this.db!.transaction(STORE_NAME, 'readwrite');
        const store = transaction.objectStore(STORE_NAME);
        const request = store.put(entry);

        request.onsuccess = () => {
          // Update memory index
          if (existingEntry) {
            this.totalSize -= existingEntry.size;
          }
          this.memoryIndex.set(key, {
            imageUpdatedAt,
            lastAccessedAt: now,
            size,
          });
          this.totalSize += size;
          resolve();
        };

        request.onerror = () => {
          console.error('IndexedDB set error:', request.error);
          resolve();
        };
      } catch (err) {
        console.error('IndexedDB set exception:', err);
        resolve();
      }
    });
  }

  /**
   * Evict entries to make room for new data.
   * Priority: full images before thumbnails, then by LRU (oldest access first).
   */
  private async evictEntries(spaceNeeded: number): Promise<void> {
    if (!this.db) return;

    // Build list of entries sorted by eviction priority
    const entries: Array<{
      key: CacheKey;
      variant: ImageVariant;
      cardId: number;
      lastAccessedAt: number;
      size: number;
    }> = [];

    for (const [key, value] of this.memoryIndex.entries()) {
      const [variant, cardIdStr] = key.split(':') as [ImageVariant, string];
      entries.push({
        key,
        variant,
        cardId: parseInt(cardIdStr, 10),
        lastAccessedAt: value.lastAccessedAt,
        size: value.size,
      });
    }

    // Sort by priority: full images first, then by lastAccessedAt (oldest first)
    entries.sort((a, b) => {
      // Full images have lower priority (evict first)
      if (a.variant !== b.variant) {
        return a.variant === 'full' ? -1 : 1;
      }
      // Within same variant, oldest accessed first
      return a.lastAccessedAt - b.lastAccessedAt;
    });

    // Calculate how much we need to free (with some buffer)
    let targetToFree = spaceNeeded + (MAX_CACHE_SIZE_BYTES * 0.1);  // Free 10% extra
    
    // Protect thumbnail reserve - if we're low on thumbnail space, be more aggressive
    const thumbSize = Array.from(this.memoryIndex.entries())
      .filter(([k]) => k.startsWith('thumb:'))
      .reduce((sum, [, v]) => sum + v.size, 0);
    
    if (thumbSize > THUMBNAIL_RESERVE_BYTES * 0.8) {
      // Thumbnails taking too much space, prioritize keeping them by evicting more full images
      targetToFree = Math.max(targetToFree, spaceNeeded * 2);
    }

    const toDelete: Array<{ variant: ImageVariant; cardId: number }> = [];
    let freedSpace = 0;

    for (const entry of entries) {
      if (freedSpace >= targetToFree) break;
      toDelete.push({ variant: entry.variant, cardId: entry.cardId });
      freedSpace += entry.size;
    }

    if (toDelete.length === 0) return;

    // Batch delete from IndexedDB
    return new Promise((resolve) => {
      try {
        const transaction = this.db!.transaction(STORE_NAME, 'readwrite');
        const store = transaction.objectStore(STORE_NAME);

        let completed = 0;
        const total = toDelete.length;

        for (const { variant, cardId } of toDelete) {
          const request = store.delete([variant, cardId]);
          request.onsuccess = () => {
            const key: CacheKey = `${variant}:${cardId}`;
            const entry = this.memoryIndex.get(key);
            if (entry) {
              this.totalSize -= entry.size;
              this.memoryIndex.delete(key);
            }
            completed++;
            if (completed === total) {
              resolve();
            }
          };
          request.onerror = () => {
            completed++;
            if (completed === total) {
              resolve();
            }
          };
        }
      } catch (err) {
        console.error('IndexedDB evict exception:', err);
        resolve();
      }
    });
  }
}

// Singleton instance
export const persistentImageCache = new PersistentImageCache();
