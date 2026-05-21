/**
 * PlinkoBoard — Coin Drop animation board (record-and-replay design).
 *
 * Coordinate system: fixed 380×460 logical units; the wrapper element scales
 * the board via CSS aspect-ratio so positions map directly to percentages.
 *
 * Determinism strategy (server-authoritative bucket alignment):
 *   1. The server picks the target bucket (`bucket_index`) via weighted RNG.
 *   2. For each requested drop we run ONE offscreen Matter.js scout engine
 *      with the full peg / wall / divider layout, trying small variations of
 *      (spawnX, vx) until a simulated coin lands in the target bucket. While
 *      the winning attempt simulates, we record the full per-substep
 *      trajectory (x, y, angle) into a Float32Array plus a list of
 *      (peg_index, frame) collision events. The scout engine is then torn
 *      down — it never animates anything visible.
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
import Matter from 'matter-js';
import {
  useEffect,
  useImperativeHandle,
  useMemo,
  useRef,
  forwardRef,
  useState,
} from 'react';

const BOARD_W = 380;
const BOARD_H = 460;
const PEG_RADIUS = 5;
const COIN_RADIUS = 12;
const BUCKET_ROW_HEIGHT = 52;
const TOP_MARGIN = 36;
const SIDE_MARGIN = 26;
const BOTTOM_PEG_MARGIN = BUCKET_ROW_HEIGHT + 30;
const PEG_LIT_MS = 160;

const COIN_NON_COLLIDING_GROUP = -1; // negative group = never collide with same group

interface PegPos {
  x: number;
  y: number;
}

interface PegHit {
  pegIndex: number;
  /** Substep index (1-based; matches frames sampled AFTER Engine.update). */
  frame: number;
}

/**
 * A recorded coin trajectory. `frames` packs [x, y, angle] per substep,
 * length = (landedFrame + 1) * 3 (frame 0 is the spawn snapshot).
 */
interface RecordedPath {
  frames: Float32Array;
  landedFrame: number;
  pegHits: PegHit[];
  bucketIndex: number;
}

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

/* --------------------------- Peg layout ------------------------------ */

/**
 * Pyramid (classic Plinko / Galton) layout: row r has r+1 pegs.
 * Top row = 1 peg (apex), bottom row = `rows` pegs spanning the playfield.
 * The horizontal peg spacing is constant across all rows so each peg sits
 * exactly between two pegs in the row below.
 *
 * Stalls on centered pegs are prevented by `findSpawnParams`, which always
 * spawns the coin off-axis by ≥ PEG_RADIUS + COIN_RADIUS px and rejects any
 * trajectory that stalls vertically for more than STALL_FRAMES.
 */
function buildPegLayout(rows: number): PegPos[] {
  const usableHeight = BOARD_H - TOP_MARGIN - BOTTOM_PEG_MARGIN;
  const rowSpacing = usableHeight / Math.max(1, rows - 1);
  const usableWidth = BOARD_W - SIDE_MARGIN * 2;
  // Bottom row has `rows` pegs → `rows - 1` gaps span the usable width.
  const colSpacing = usableWidth / Math.max(1, rows - 1);
  const centerX = BOARD_W / 2;
  const pegs: PegPos[] = [];
  for (let r = 0; r < rows; r++) {
    const cols = r + 1;
    const rowWidth = (cols - 1) * colSpacing;
    const xStart = centerX - rowWidth / 2;
    const y = TOP_MARGIN + r * rowSpacing;
    for (let c = 0; c < cols; c++) {
      pegs.push({ x: xStart + c * colSpacing, y });
    }
  }
  return pegs;
}

/* ------------------------ Engine construction ------------------------ */

function buildEngine(pegs: PegPos[], bucketCount: number): Matter.Engine {
  const engine = Matter.Engine.create({
    gravity: { x: 0, y: 1, scale: 0.0014 },
  });

  // Side walls + floor (top is open). Low restitution dampens edge bouncing.
  const wallOpts = { isStatic: true, restitution: 0.05, friction: 0.4 };
  const walls = [
    Matter.Bodies.rectangle(-10, BOARD_H / 2, 20, BOARD_H, wallOpts),
    Matter.Bodies.rectangle(BOARD_W + 10, BOARD_H / 2, 20, BOARD_H, wallOpts),
    Matter.Bodies.rectangle(BOARD_W / 2, BOARD_H + 10, BOARD_W, 20, wallOpts),
  ];
  Matter.Composite.add(engine.world, walls);

  // Pegs. Higher restitution + a touch of friction keep coins bouncing off
  // cleanly instead of resting on top of a peg.
  const pegBodies = pegs.map((p, i) =>
    Matter.Bodies.circle(p.x, p.y, PEG_RADIUS, {
      isStatic: true,
      restitution: 0.65,
      friction: 0.05,
      label: `peg:${i}`,
    })
  );
  Matter.Composite.add(engine.world, pegBodies);

  // Bucket dividers — thin vertical walls between buckets so a coin lands
  // cleanly in one bucket instead of skipping along the row of separators.
  const dividerThickness = 2;
  const dividerTop = BOARD_H - BUCKET_ROW_HEIGHT;
  const dividerHeight = BUCKET_ROW_HEIGHT;
  for (let i = 1; i < bucketCount; i++) {
    const x = (BOARD_W / bucketCount) * i;
    const divider = Matter.Bodies.rectangle(
      x,
      dividerTop + dividerHeight / 2,
      dividerThickness,
      dividerHeight,
      { isStatic: true, restitution: 0.05, friction: 0.5, label: 'divider' }
    );
    Matter.Composite.add(engine.world, divider);
  }

  return engine;
}

/** Spawn coin above the visible top edge so it falls into view. */
const SPAWN_Y = -COIN_RADIUS * 2;

function makeCoinBody(x: number, vx: number): Matter.Body {
  return Matter.Bodies.circle(x, SPAWN_Y, COIN_RADIUS, {
    restitution: 0.45,
    friction: 0.01,
    frictionAir: 0.012,
    density: 0.004,
    collisionFilter: { group: COIN_NON_COLLIDING_GROUP },
    label: 'coin',
    velocity: { x: vx, y: 0 },
  });
}

/** Map landing x → bucket index (0..bucketCount-1). */
function landingBucket(x: number, bucketCount: number): number {
  const idx = Math.floor((x / BOARD_W) * bucketCount);
  return Math.max(0, Math.min(bucketCount - 1, idx));
}

/* --------------- Offline path recording (deterministic) -------------- */

const MAX_SEARCH_ATTEMPTS = 200;
const SIM_STEPS = 600;
const SIM_DT = 1000 / 60;
// Reject any scout attempt where the coin's max-Y doesn't advance by at least
// MIN_PROGRESS px within STALL_FRAMES consecutive frames. Filters out hangy
// paths so the visible coin always drops fluidly.
const STALL_FRAMES = 18; // 0.3s at 60fps — reject only long hangs
const MIN_PROGRESS = 1.5; // virtual px
// Minimum horizontal offset from center axis so the coin never spawns directly
// above a centered peg (avoids vertical-stack stalls on any row with a center peg).
// A small minimum offset (~2 px) plus jitter keeps it just off dead-center so
// any hang is short and asymmetric. The scout's stall rejection filters out
// trajectories where the hang is too long.
const SPAWN_MIN_OFFSET = 2; // virtual px
const SPAWN_MAX_OFFSET = 8; // virtual px

/**
 * Build a fresh scout engine, search for (spawnX, vx) that lands a coin in
 * `targetBucket`, and return the full recorded trajectory of the winning
 * attempt — which the on-screen animation then replays.
 *
 * The scout engine is reused across attempts within this call (cheap and
 * matches the engine's intended usage); residual state across attempts does
 * NOT cause bucket mismatch anymore because there is no separate "live"
 * engine to diverge from — the recorded path IS the visible animation.
 */
function recordPath(
  pegs: PegPos[],
  bucketCount: number,
  targetBucket: number
): RecordedPath {
  const scout = buildEngine(pegs, bucketCount);

  let currentFrame = 0;
  let recordingPegHits: PegHit[] = [];
  const onCollide = (event: Matter.IEventCollision<Matter.Engine>) => {
    for (const pair of event.pairs) {
      const pegBody =
        pair.bodyA.label?.startsWith('peg:') ? pair.bodyA :
        pair.bodyB.label?.startsWith('peg:') ? pair.bodyB : null;
      if (!pegBody) continue;
      const idx = Number(pegBody.label.slice(4));
      recordingPegHits.push({ pegIndex: idx, frame: currentFrame });
    }
  };
  Matter.Events.on(scout, 'collisionStart', onCollide);

  const cleanup = () => {
    Matter.Events.off(scout, 'collisionStart', onCollide);
    Matter.World.clear(scout.world, false);
    Matter.Engine.clear(scout);
  };

  // Reused across attempts to avoid allocating a fresh 7KB typed array per
  // try (worst-case ~200 tries/drop). We only slice into a right-sized
  // buffer when we actually return a winning path.
  const scratchBuffer = new Float32Array((SIM_STEPS + 1) * 3);

  /**
   * Run one attempt. Returns the recorded path iff the coin settled in the
   * target bucket with a non-degenerate (non-exploded, non-stalled) trajectory;
   * returns null otherwise. Caller just retries until non-null or exhaustion.
   */
  const tryAttempt = (spawnX: number, vx: number): RecordedPath | null => {
    recordingPegHits = [];
    currentFrame = 0;

    const coin = makeCoinBody(spawnX, vx);
    Matter.Composite.add(scout.world, coin);

    let bufIdx = 0;
    scratchBuffer[bufIdx++] = coin.position.x;
    scratchBuffer[bufIdx++] = coin.position.y;
    scratchBuffer[bufIdx++] = coin.angle;

    let landedFrame = -1;
    let maxY = coin.position.y;
    let lastProgressStep = 0;

    for (let step = 0; step < SIM_STEPS; step++) {
      currentFrame = step + 1;
      Matter.Engine.update(scout, SIM_DT);
      const px = coin.position.x;
      const py = coin.position.y;
      const pa = coin.angle;
      scratchBuffer[bufIdx++] = px;
      scratchBuffer[bufIdx++] = py;
      scratchBuffer[bufIdx++] = pa;

      // Matter can produce NaN / Infinity when an over-constrained collision
      // resolves badly (e.g., a coin pinched between the leftmost peg and the
      // side wall — the gap is narrower than a coin's diameter, so the solver
      // can explode). Reject those — a NaN frame in playback would render as
      // a half-coin stuck in the upper-left corner (CSS `left: NaN%` →
      // `auto` → 0,0). Also reject anything that escapes the playfield.
      if (
        !Number.isFinite(px) || !Number.isFinite(py) || !Number.isFinite(pa) ||
        px < -50 || px > BOARD_W + 50 ||
        py < -200 || py > BOARD_H + 200
      ) {
        Matter.Composite.remove(scout.world, coin);
        return null;
      }

      if (py > maxY + MIN_PROGRESS) {
        maxY = py;
        lastProgressStep = step;
      } else if (step - lastProgressStep > STALL_FRAMES) {
        Matter.Composite.remove(scout.world, coin);
        return null;
      }
      if (py > BOARD_H - BUCKET_ROW_HEIGHT) {
        landedFrame = step + 1;
        break;
      }
    }

    const finalX = coin.position.x;
    Matter.Composite.remove(scout.world, coin);

    if (landedFrame < 0) return null; // ran out of sim steps without settling
    if (landingBucket(finalX, bucketCount) !== targetBucket) return null;

    return {
      frames: scratchBuffer.slice(0, bufIdx),
      landedFrame,
      pegHits: recordingPegHits.slice(),
      bucketIndex: targetBucket,
    };
  };

  for (let attempt = 0; attempt < MAX_SEARCH_ATTEMPTS; attempt++) {
    const offsetSign = Math.random() < 0.5 ? -1 : 1;
    const spawnX =
      BOARD_W / 2 +
      offsetSign * (SPAWN_MIN_OFFSET + Math.random() * (SPAWN_MAX_OFFSET - SPAWN_MIN_OFFSET));
    const vxSign = Math.random() < 0.5 ? -1 : 1;
    const vx = vxSign * (0.4 + Math.random() * 1.6); // |vx| ∈ [0.4, 2.0]

    const path = tryAttempt(spawnX, vx);
    if (path) {
      cleanup();
      return path;
    }
  }

  // Exhaustion fallback: biased spawn aimed at target side. With dividers in
  // place this usually lands in the target bucket too.
  const bucketCenter = (BOARD_W / bucketCount) * (targetBucket + 0.5);
  const direction = bucketCenter < BOARD_W / 2 ? -1 : 1;
  const biased = tryAttempt(BOARD_W / 2 + direction * SPAWN_MIN_OFFSET, direction * 1.2);
  cleanup();
  if (biased) return biased;

  // Synthetic last-resort path so playback never crashes and ALWAYS lands in
  // the target bucket. Should be effectively unreachable in practice (search
  // + biased attempt both missing is astronomically unlikely with dividers).
  const cx = (BOARD_W / bucketCount) * (targetBucket + 0.5);
  const cy = BOARD_H - BUCKET_ROW_HEIGHT;
  return {
    frames: new Float32Array([cx, cy - 30, 0, cx, cy + 1, 0]),
    landedFrame: 1,
    pegHits: [],
    bucketIndex: targetBucket,
  };
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
  /** Last rAF tick timestamp; used to detect long main-thread blocks (e.g.
   *  the synchronous scout simulation inside dropCoin) and avoid jumping
   *  in-flight coins forward by the block's full duration. */
  const lastTickMsRef = useRef<number | null>(null);
  /** pegIndex → timestamp (ms) at which the lit state expires. */
  const litPegsRef = useRef<Map<number, number>>(new Map());
  /** DOM refs for direct (non-React) style writes from the rAF tick. */
  const coinElsRef = useRef<Map<number, HTMLDivElement>>(new Map());
  const pegElsRef = useRef<(HTMLDivElement | null)[]>([]);

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

  // Animation loop only. Peg layout is computed via useMemo above; pegsRef is
  // synced inline so the imperative dropCoin handle always sees the latest.
  useEffect(() => {
    // Cap how much wall-clock time any single rAF tick can advance playback
    // by. dropCoin's recordPath runs synchronously and can block for tens of
    // ms; without this cap the next tick would jump every in-flight coin
    // forward by the full block duration, potentially snapping a near-landing
    // coin straight into its bucket. Setting the cap to ~2 frames keeps motion
    // smooth across short blocks and tab-resume events.
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

  useImperativeHandle(
    ref,
    () => ({
      dropCoin: (bucketIndex: number) => {
        return new Promise<void>((resolve) => {
          if (!pegs.length) {
            resolve();
            return;
          }
          // Guard against out-of-range bucket indices (e.g., if the server
          // ever returns an unexpected value); recordPath would otherwise
          // loop without ever matching, then fall through to synthetic.
          const safeBucket = Math.max(0, Math.min(bucketCount - 1, Math.floor(bucketIndex)));
          // Single scout simulation (with full recording) per drop. The scout
          // engine is built fresh and torn down inside recordPath() so no
          // state leaks between drops.
          const path = recordPath(pegs, bucketCount, safeBucket);
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
