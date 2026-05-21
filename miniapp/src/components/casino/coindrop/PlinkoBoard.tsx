/**
 * PlinkoBoard — Coin Drop animation board (record-and-replay design).
 *
 * Coordinate system: fixed 380×460 logical units; the wrapper element scales
 * the board via CSS aspect-ratio so positions map directly to percentages.
 *
 * Determinism strategy (server-authoritative bucket alignment):
 *   1. The server picks the target bucket (`bucket_index`) via weighted RNG.
 *   2. For each requested drop we ask a Web Worker (plinkoPath.worker.ts) to
 *      run ONE offscreen Matter.js scout engine with the full peg / wall /
 *      divider layout, trying small variations of (spawnX, vx) until a
 *      simulated coin lands in the target bucket. While the winning attempt
 *      simulates, the worker records the full per-substep trajectory
 *      (x, y, angle) into a Float32Array plus a list of (peg_index, frame)
 *      collision events, then transfers it back to the main thread
 *      (zero-copy via the Transferable buffer). The scout never animates
 *      anything visible and never blocks the main thread, so in-flight coins
 *      keep rendering at 60fps while the next drop is being prepared.
 *   3. The on-screen coin is NOT driven by a live physics engine. It is
 *      animated via requestAnimationFrame by interpolating the recorded path
 *      based on real elapsed time, so the visible coin lands in exactly the
 *      bucket the scout predicted — by construction.
 *   4. Concurrent drops are independent because each coin owns its own
 *      recorded path; there is no shared physics state at playback time.
 *
 * Why record-and-replay (vs. running a separate live engine and trusting it
 * to match the scout): two Matter engines with identical inputs do not produce
 * bit-identical trajectories across hundreds of substeps — internal RNG
 * histories, detector pair caches, and rAF accumulator backlog drops all
 * cause drift. Wall sliding amplifies the drift, which historically caused
 * coins to appear to land in the wrong bucket near the edges. Playing back a
 * single deterministic simulation removes the failure mode entirely.
 */
import {
  useEffect,
  useImperativeHandle,
  useMemo,
  useRef,
  forwardRef,
  useState,
} from 'react';
import {
  BOARD_W,
  BOARD_H,
  PEG_RADIUS,
  COIN_RADIUS,
  SIM_DT,
  buildPegLayout,
  recordPath as recordPathInline,
  type PegPos,
  type RecordedPath,
} from './plinkoPhysics';
import type {
  PlinkoRequestMsg,
  PlinkoResponseMsg,
} from './plinkoWorkerProtocol';

const PEG_LIT_MS = 160;

interface ActiveCoin {
  id: number;
  path: RecordedPath;
  startMs: number;
  /** Cursor into path.pegHits — next hit not yet emitted. */
  nextPegHit: number;
  fired: boolean;
  resolve?: () => void;
}

export interface PlinkoBoardHandle {
  /** Spawn a coin that will land in `bucketIndex`. Resolves when the coin enters the bucket. */
  dropCoin: (bucketIndex: number) => Promise<void>;
}

interface PlinkoBoardProps {
  pegRows: number;
  bucketCount: number;
  bucketMultipliers: number[];
  onLanding?: (bucketIndex: number) => void;
}


/* ---------------------------- Component ------------------------------ */

const PlinkoBoard = forwardRef<PlinkoBoardHandle, PlinkoBoardProps>(function PlinkoBoard(
  { pegRows, bucketCount, bucketMultipliers, onLanding },
  ref
) {
  /** id → active coin (path + playback cursor). */
  const activeCoinsRef = useRef<Map<number, ActiveCoin>>(new Map());
  const nextCoinIdRef = useRef(1);
  const rafRef = useRef<number | null>(null);
  /** Last rAF tick timestamp; used to detect long main-thread blocks
   *  (background tab, OS throttling, GC pause) and avoid jumping in-flight
   *  coins forward by the block's full duration. */
  const lastTickMsRef = useRef<number | null>(null);
  /** pegIndex → timestamp (ms) at which the lit state expires. */
  const litPegsRef = useRef<Map<number, number>>(new Map());
  /** DOM refs for direct (non-React) style writes from the rAF tick. */
  const coinElsRef = useRef<Map<number, HTMLDivElement>>(new Map());
  const pegElsRef = useRef<(HTMLDivElement | null)[]>([]);
  /** Web Worker that runs the Matter.js scout off the main thread. */
  const workerRef = useRef<Worker | null>(null);
  /** Pending compute requests: correlator id → resolver. */
  const pendingPathsRef = useRef<
    Map<number, { resolve: (p: RecordedPath) => void; reject: (e: unknown) => void }>
  >(new Map());
  const nextRequestIdRef = useRef(1);

  // React state holds ONLY identifiers (rarely changing): coin add/remove and
  // bucket flashes. Positions, rotations, and peg lit state are written
  // directly to the DOM in the rAF tick so animation never triggers a React
  // re-render and can never be raced by React state batching (the source of
  // the brief "landed coin reappears for one frame" glitch).
  const [coinIds, setCoinIds] = useState<number[]>([]);
  // Per-bucket monotonic flash counter. Each landing bumps the counter for that
  // bucket; the renderer mounts a glow element keyed by the counter so React
  // restarts the CSS fade animation by remount. No timeout needed — the
  // animation handles the entire visual lifecycle (snap in, gradual fade out).
  const [bucketFlashKeys, setBucketFlashKeys] = useState<number[]>(() =>
    new Array(bucketCount).fill(0),
  );
  const pegs = useMemo(() => buildPegLayout(pegRows), [pegRows]);
  // Keep pegElsRef sized to the current layout so a shrink (lower pegRows)
  // doesn't leave orphan refs at higher indices.
  if (pegElsRef.current.length !== pegs.length) {
    pegElsRef.current.length = pegs.length;
  }

  // Direct-DOM write helpers. Skip when an element ref is missing (between
  // React render and ref attach) or when a value is non-finite (would emit
  // CSS `left: NaN%` → falls back to auto → renders at upper-left).
  const writeCoinStyle = (el: HTMLDivElement, x: number, y: number, angle: number) => {
    if (!Number.isFinite(x) || !Number.isFinite(y) || !Number.isFinite(angle)) {
      if (el.style.visibility !== 'hidden') el.style.visibility = 'hidden';
      return;
    }
    if (el.style.visibility === 'hidden') el.style.visibility = '';
    el.style.left = `${(x / BOARD_W) * 100}%`;
    el.style.top = `${(y / BOARD_H) * 100}%`;
    el.style.transform = `translate(-50%, -50%) rotate(${angle}rad)`;
  };

  /**
   * Worker lifecycle. The worker runs Matter.js scout simulations (recordPath)
   * off the main thread so a drop click never blocks animation of in-flight
   * coins. On worker failure, we reject all pending requests; dropCoin's
   * caller falls back to an inline (main-thread) recordPath for that one
   * request, and a fresh worker is started for subsequent drops.
   */
  useEffect(() => {
    let cancelled = false;

    const spawnWorker = () => {
      const w = new Worker(
        new URL('./plinkoPath.worker.ts', import.meta.url),
        { type: 'module' }
      );
      w.onmessage = (e: MessageEvent<PlinkoResponseMsg>) => {
        const msg = e.data;
        if (!msg || msg.type !== 'result') return;
        const pending = pendingPathsRef.current.get(msg.id);
        if (!pending) return;
        pendingPathsRef.current.delete(msg.id);
        pending.resolve({
          frames: msg.frames,
          landedFrame: msg.landedFrame,
          pegHits: msg.pegHits,
          bucketIndex: msg.bucketIndex,
        });
      };
      w.onerror = (err) => {
        // Reject all pending; caller falls back to inline compute.
        // eslint-disable-next-line no-console
        console.error('[PlinkoBoard] worker error, falling back to main-thread compute', err);
        const pending = pendingPathsRef.current;
        pendingPathsRef.current = new Map();
        pending.forEach((p) => p.reject(err));
        try { w.terminate(); } catch { /* noop */ }
        if (!cancelled) {
          workerRef.current = spawnWorker();
        }
      };
      return w;
    };

    workerRef.current = spawnWorker();

    return () => {
      cancelled = true;
      try { workerRef.current?.terminate(); } catch { /* noop */ }
      workerRef.current = null;
      const pending = pendingPathsRef.current;
      pendingPathsRef.current = new Map();
      pending.forEach((p) => p.reject(new Error('PlinkoBoard unmounted')));
    };
  }, []);

  // Animation loop only. Peg layout is computed via useMemo above.
  useEffect(() => {
    // Cap how much wall-clock time any single rAF tick can advance playback
    // by. With the worker, drops no longer block the main thread, but other
    // sources (tab switch, OS throttling, GC, Telegram WebView background
    // throttling) can still stall rAF for tens of ms; without this cap the
    // next tick would jump every in-flight coin forward by the full stall
    // duration. Capping at ~2 frames keeps motion smooth across short blocks.
    const MAX_TICK_DELTA_MS = 1000 / 30;

    const tick = (nowMs: number) => {
      // Detect long blocks and shift already-flying coins forward only by
      // the capped delta, effectively "pausing" them during the block. Coins
      // added during the block (startMs > cutoff) are exempted so they still
      // begin playback from frame 0 instead of starting mid-air.
      const last = lastTickMsRef.current;
      if (last != null) {
        const actualDelta = nowMs - last;
        if (actualDelta > MAX_TICK_DELTA_MS) {
          const skip = actualDelta - MAX_TICK_DELTA_MS;
          const cutoff = nowMs - MAX_TICK_DELTA_MS;
          activeCoinsRef.current.forEach((coin) => {
            if (coin.startMs < cutoff) coin.startMs += skip;
          });
        }
      }
      lastTickMsRef.current = nowMs;

      // Update peg lit state directly on DOM (toggle .lit class). Iterate the
      // map; expired entries are removed AND un-lit in the same pass.
      if (litPegsRef.current.size > 0) {
        litPegsRef.current.forEach((expiry, idx) => {
          const el = pegElsRef.current[idx];
          if (expiry <= nowMs) {
            litPegsRef.current.delete(idx);
            if (el) el.classList.remove('lit');
          }
        });
      }

      activeCoinsRef.current.forEach((coin, id) => {
        // max(0,…) so a coin whose startMs is microseconds in the future
        // (set by dropCoin between rAF ticks) still renders at frame 0
        // rather than reading a negative index.
        const elapsedMs = Math.max(0, nowMs - coin.startMs);
        // Frame index (float) into the recorded buffer. Clamped to the
        // landed frame so playback can't read past the recorded range
        // before we fire the bucket event.
        const frameFloat = elapsedMs / SIM_DT;
        const landed = coin.path.landedFrame;
        const clamped = Math.min(frameFloat, landed);
        const f0 = Math.floor(clamped);
        const t = clamped - f0;
        const frames = coin.path.frames;
        const i0 = f0 * 3;
        // f0+1 may equal landed; clamp index to last sample so we don't
        // read past the buffer end (Float32Array would just return 0).
        const i1 = Math.min((f0 + 1) * 3, landed * 3);
        const x = frames[i0] + (frames[i1] - frames[i0]) * t;
        const y = frames[i0 + 1] + (frames[i1 + 1] - frames[i0 + 1]) * t;
        // Angle interpolation: small per-frame deltas at 60Hz mean naive
        // lerp is visually correct without unwrap-tracking.
        const a = frames[i0 + 2] + (frames[i1 + 2] - frames[i0 + 2]) * t;

        // Emit any peg-light events whose recorded frame is now in the past.
        while (
          coin.nextPegHit < coin.path.pegHits.length &&
          coin.path.pegHits[coin.nextPegHit].frame <= clamped
        ) {
          const hit = coin.path.pegHits[coin.nextPegHit];
          litPegsRef.current.set(hit.pegIndex, nowMs + PEG_LIT_MS);
          const pegEl = pegElsRef.current[hit.pegIndex];
          if (pegEl) pegEl.classList.add('lit');
          coin.nextPegHit++;
        }

        if (!coin.fired && frameFloat >= landed) {
          coin.fired = true;
          const bi = coin.path.bucketIndex;
          setBucketFlashKeys((prev) => {
            const next = prev.slice();
            next[bi] = (next[bi] ?? 0) + 1;
            return next;
          });
          onLanding?.(bi);
          activeCoinsRef.current.delete(id);
          coin.resolve?.();
          // Remove from rendered list. Hide the DOM element immediately so it
          // doesn't paint one extra frame at the landing position before React
          // unmounts it on the next commit — this is what eliminates the
          // "ghost coin above the bucket" glitch.
          const el = coinElsRef.current.get(id);
          if (el) el.style.visibility = 'hidden';
          setCoinIds((ids) => ids.filter((i) => i !== id));
          return;
        }

        const el = coinElsRef.current.get(id);
        if (el) writeCoinStyle(el, x, y, a);
      });

      rafRef.current = requestAnimationFrame(tick);
    };
    rafRef.current = requestAnimationFrame(tick);

    return () => {
      if (rafRef.current != null) cancelAnimationFrame(rafRef.current);
      rafRef.current = null;
      lastTickMsRef.current = null;
      // Resolve any in-flight drop promises so callers awaiting `dropCoin`
      // don't hang forever if props change (e.g., pegRows/bucketCount/onLanding)
      // while a coin is still animating.
      activeCoinsRef.current.forEach((coin) => coin.resolve?.());
      activeCoinsRef.current.clear();
      litPegsRef.current.clear();
      setCoinIds([]);
    };
  }, [pegRows, bucketCount, onLanding]);

  /**
   * Send a scout-path request to the worker; resolves with the RecordedPath
   * once the worker responds. Rejects if the worker crashes or unmounts
   * before responding — callers should fall back to inline compute.
   */
  const requestPath = (
    pegList: PegPos[],
    bucketCount: number,
    targetBucket: number
  ): Promise<RecordedPath> => {
    return new Promise<RecordedPath>((resolve, reject) => {
      const w = workerRef.current;
      if (!w) {
        reject(new Error('worker unavailable'));
        return;
      }
      const id = nextRequestIdRef.current++;
      pendingPathsRef.current.set(id, { resolve, reject });
      const req: PlinkoRequestMsg = {
        type: 'compute',
        id,
        pegs: pegList,
        bucketCount,
        targetBucket,
      };
      try {
        w.postMessage(req);
      } catch (err) {
        pendingPathsRef.current.delete(id);
        reject(err);
      }
    });
  };

  useImperativeHandle(
    ref,
    () => ({
      dropCoin: async (bucketIndex: number) => {
        if (!pegs.length) return;
        const safeBucket = Math.max(0, Math.min(bucketCount - 1, Math.floor(bucketIndex)));

        // Request the scout path from the worker. On worker failure or
        // unmount, fall back to inline (main-thread) recordPath for this
        // single request so the user still gets their coin.
        let path: RecordedPath;
        try {
          path = await requestPath(pegs, bucketCount, safeBucket);
        } catch {
          path = recordPathInline(pegs, bucketCount, safeBucket);
        }

        // Component may have unmounted while we awaited the worker.
        if (workerRef.current === null && pendingPathsRef.current.size === 0) {
          // best-effort: still mount the coin only if the rAF loop is alive
          // (rafRef is cleared on unmount); otherwise just bail silently.
          if (rafRef.current == null) return;
        }

        return new Promise<void>((resolve) => {
          const id = nextCoinIdRef.current++;
          activeCoinsRef.current.set(id, {
            id,
            path,
            startMs: performance.now(),
            nextPegHit: 0,
            fired: false,
            resolve,
          });
          // Mount the coin div. Initial position is applied in the ref
          // callback so the DOM is correct on first paint, not at (0,0).
          setCoinIds((ids) => [...ids, id]);
        });
      },
    }),
    [bucketCount, pegs]
  );

  // Precomputed peg styles — change only when the layout itself changes.
  const pegStyles = useMemo(
    () =>
      pegs.map((p) => ({
        left: `${(p.x / BOARD_W) * 100}%`,
        top: `${(p.y / BOARD_H) * 100}%`,
        width: `${((PEG_RADIUS * 2) / BOARD_W) * 100}%`,
        height: `${((PEG_RADIUS * 2) / BOARD_H) * 100}%`,
      })),
    [pegs]
  );

  const coinSizeStyle = useMemo<React.CSSProperties>(
    () => ({
      width: `${((COIN_RADIUS * 2) / BOARD_W) * 100}%`,
      height: `${((COIN_RADIUS * 2) / BOARD_H) * 100}%`,
      // Hidden until the ref callback runs writeCoinStyle with the spawn
      // frame, so the coin never paints at (0,0) on first mount.
      visibility: 'hidden',
    }),
    []
  );

  return (
    <div className="coindrop-board-wrapper">
      <div className="coindrop-stage">
        {pegs.map((_p, i) => (
          <div
            key={`peg-${i}`}
            className="coindrop-peg"
            style={pegStyles[i]}
            ref={(el) => {
              pegElsRef.current[i] = el;
            }}
          />
        ))}
        {coinIds.map((id) => (
          <div
            key={`coin-${id}`}
            className="coindrop-coin"
            style={coinSizeStyle}
            ref={(el) => {
              if (el) {
                coinElsRef.current.set(id, el);
                // Apply spawn-frame position immediately so the coin appears
                // at the top of the board on first paint, not at (0, 0).
                const coin = activeCoinsRef.current.get(id);
                if (coin) {
                  const f = coin.path.frames;
                  writeCoinStyle(el, f[0], f[1], f[2]);
                }
              } else {
                coinElsRef.current.delete(id);
              }
            }}
          />
        ))}
      </div>
      <div className="coindrop-bucket-row">
        {bucketMultipliers.map((m, i) => {
          const flashKey = bucketFlashKeys[i] ?? 0;
          return (
            <div key={`bucket-${i}`} className="coindrop-bucket" data-mult={m}>
              {flashKey > 0 && (
                <span
                  key={flashKey}
                  className="coindrop-bucket-glow"
                  aria-hidden="true"
                />
              )}
              {m}x
            </div>
          );
        })}
      </div>
    </div>
  );
});

export default PlinkoBoard;
