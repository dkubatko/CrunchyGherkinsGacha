/**
 * Persistent IndexedDB-backed image cache with LRU eviction.
 */

export type ImageVariant = 'full' | 'thumb';

interface CacheEntry {
  cardId: number;
  variant: ImageVariant;
  data: string;
  imageUpdatedAt: string | null;
  cachedAt: number;
  lastAccessedAt: number;
  size: number;
}

type CacheKey = `${ImageVariant}:${number}`;

const DB_NAME = 'cardImageCache';
const DB_VERSION = 1;
const STORE_NAME = 'images';
const MAX_CACHE_SIZE = 30 * 1024 * 1024; // 30MB

// Promisify IDBRequest
const promisify = <T>(request: IDBRequest<T>): Promise<T> =>
  new Promise((resolve, reject) => {
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });

class PersistentImageCache {
  private dbPromise: Promise<IDBDatabase | null>;
  private index = new Map<CacheKey, { imageUpdatedAt: string | null; size: number; lastAccessedAt: number }>();
  private totalSize = 0;

  constructor() {
    this.dbPromise = this.openDatabase();
  }

  private async openDatabase(): Promise<IDBDatabase | null> {
    if (typeof indexedDB === 'undefined') return null;

    return new Promise((resolve) => {
      const timeout = setTimeout(() => resolve(null), 3000);

      const request = indexedDB.open(DB_NAME, DB_VERSION);
      
      request.onerror = () => { clearTimeout(timeout); resolve(null); };
      
      request.onupgradeneeded = (e) => {
        const db = (e.target as IDBOpenDBRequest).result;
        if (!db.objectStoreNames.contains(STORE_NAME)) {
          db.createObjectStore(STORE_NAME, { keyPath: ['variant', 'cardId'] });
        }
      };

      request.onsuccess = async () => {
        clearTimeout(timeout);
        const db = request.result;
        await this.buildIndex(db);
        resolve(db);
      };
    });
  }

  private async buildIndex(db: IDBDatabase): Promise<void> {
    const tx = db.transaction(STORE_NAME, 'readonly');
    const store = tx.objectStore(STORE_NAME);
    const entries: CacheEntry[] = await promisify(store.getAll());

    this.index.clear();
    this.totalSize = 0;

    for (const entry of entries) {
      const key: CacheKey = `${entry.variant}:${entry.cardId}`;
      this.index.set(key, {
        imageUpdatedAt: entry.imageUpdatedAt,
        size: entry.size,
        lastAccessedAt: entry.lastAccessedAt,
      });
      this.totalSize += entry.size;
    }
  }

  private isStale(cardId: number, variant: ImageVariant, serverTimestamp: string | null): boolean {
    if (!serverTimestamp) return false;
    const entry = this.index.get(`${variant}:${cardId}`);
    if (!entry?.imageUpdatedAt) return true;
    return new Date(entry.imageUpdatedAt) < new Date(serverTimestamp);
  }

  async get(cardId: number, variant: ImageVariant, serverTimestamp: string | null = null): Promise<string | null> {
    const db = await this.dbPromise;
    if (!db) return null;

    const key: CacheKey = `${variant}:${cardId}`;
    if (!this.index.has(key)) return null;
    if (this.isStale(cardId, variant, serverTimestamp)) return null;

    const tx = db.transaction(STORE_NAME, 'readwrite');
    const store = tx.objectStore(STORE_NAME);
    const entry: CacheEntry | undefined = await promisify(store.get([variant, cardId]));

    if (!entry) {
      this.index.delete(key);
      return null;
    }

    // Update LRU timestamp
    entry.lastAccessedAt = Date.now();
    store.put(entry);
    
    const indexEntry = this.index.get(key);
    if (indexEntry) indexEntry.lastAccessedAt = entry.lastAccessedAt;

    return entry.data;
  }

  async set(cardId: number, variant: ImageVariant, data: string, imageUpdatedAt: string | null): Promise<void> {
    const db = await this.dbPromise;
    if (!db) return;

    const key: CacheKey = `${variant}:${cardId}`;
    const size = data.length;
    const existing = this.index.get(key);
    const sizeIncrease = existing ? size - existing.size : size;

    if (this.totalSize + sizeIncrease > MAX_CACHE_SIZE) {
      await this.evict(db, sizeIncrease);
    }

    const now = Date.now();
    const entry: CacheEntry = {
      cardId,
      variant,
      data,
      imageUpdatedAt,
      cachedAt: now,
      lastAccessedAt: now,
      size,
    };

    const tx = db.transaction(STORE_NAME, 'readwrite');
    await promisify(tx.objectStore(STORE_NAME).put(entry));

    if (existing) this.totalSize -= existing.size;
    this.index.set(key, { imageUpdatedAt, size, lastAccessedAt: now });
    this.totalSize += size;
  }

  private async evict(db: IDBDatabase, spaceNeeded: number): Promise<void> {
    // Sort: full images first, then by oldest access
    const entries = Array.from(this.index.entries())
      .map(([key, val]) => {
        const [variant, id] = key.split(':') as [ImageVariant, string];
        return { key, variant, cardId: parseInt(id, 10), ...val };
      })
      .sort((a, b) => {
        if (a.variant !== b.variant) return a.variant === 'full' ? -1 : 1;
        return a.lastAccessedAt - b.lastAccessedAt;
      });

    const toDelete: Array<{ variant: ImageVariant; cardId: number; key: CacheKey; size: number }> = [];
    let freed = 0;
    const target = spaceNeeded + MAX_CACHE_SIZE * 0.1;

    for (const entry of entries) {
      if (freed >= target) break;
      toDelete.push(entry);
      freed += entry.size;
    }

    if (toDelete.length === 0) return;

    const tx = db.transaction(STORE_NAME, 'readwrite');
    const store = tx.objectStore(STORE_NAME);

    for (const { variant, cardId, key, size } of toDelete) {
      store.delete([variant, cardId]);
      this.index.delete(key);
      this.totalSize -= size;
    }

    await new Promise<void>((resolve, reject) => {
      tx.oncomplete = () => resolve();
      tx.onerror = () => reject(tx.error);
    });
  }
}

export const persistentImageCache = new PersistentImageCache();

