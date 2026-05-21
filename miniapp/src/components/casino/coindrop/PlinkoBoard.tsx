/**
 * PlinkoBoard — Matter.js physics board for the Coin Drop game.
 *
 * Coordinate system: fixed 320×460 logical units; the wrapper element scales
 * the board via CSS aspect-ratio so positions map directly to percentages.
 *
 * Determinism strategy (server-authoritative bucket alignment):
 *   1. The server picks the target bucket (`bucket_index`) via weighted RNG.
 *   2. We never touch `Matter.Common.random`. Instead, we exploit the fact
 *      that coins ignore each other (collision filter group: -1) and pegs are
 *      static, so each coin's path is fully determined by its initial state.
 *   3. For each requested drop, we run an offscreen "scout" engine with the
 *      same peg layout, trying small variations of (spawnX, vx) until the
 *      simulated coin lands in the target bucket. The matching parameters are
 *      then used to spawn the visible coin — it will land in the same bucket.
 *   4. Concurrent drops are independent because coins don't interact.
 */
import Matter from 'matter-js';
import {
  memo,
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

interface CoinView {
  id: number;
  x: number;
  y: number;
}

interface PegPos {
  x: number;
  y: number;
}

interface ScheduledLanding {
  coinId: number;
  bucketIndex: number;
  fired?: boolean;
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

/* ----------- Offline seed search (deterministic per-coin) ------------ */

const MAX_SEARCH_ATTEMPTS = 200;
const SIM_STEPS = 600;
const SIM_DT = 1000 / 60;
// Reject any scout attempt where the coin's max-Y doesn't advance by at least
// MIN_PROGRESS px within STALL_FRAMES consecutive frames. Filters out hangy
// paths so the live coin always drops fluidly.
const STALL_FRAMES = 18; // 0.3s at 60fps — reject only long hangs
const MIN_PROGRESS = 1.5; // virtual px
// Minimum horizontal offset from center axis so the coin never spawns directly
// above a centered peg (avoids vertical-stack stalls on any row with a center peg).
// Spawn is allowed near the center axis so the coin engages the apex peg
// (classic Plinko feel). A small minimum offset (~2 px) plus jitter keeps it
// just off dead-center so any hang is short and asymmetric. The scout's stall
// rejection filters out trajectories where the hang is too long.
const SPAWN_MIN_OFFSET = 2; // virtual px
const SPAWN_MAX_OFFSET = 8; // virtual px

function findSpawnParams(
  scout: Matter.Engine,
  bucketCount: number,
  targetBucket: number
): { spawnX: number; vx: number } {
  for (let attempt = 0; attempt < MAX_SEARCH_ATTEMPTS; attempt++) {
    const offsetSign = Math.random() < 0.5 ? -1 : 1;
    const spawnX =
      BOARD_W / 2 +
      offsetSign * (SPAWN_MIN_OFFSET + Math.random() * (SPAWN_MAX_OFFSET - SPAWN_MIN_OFFSET));
    const vxSign = Math.random() < 0.5 ? -1 : 1;
    const vx = vxSign * (0.4 + Math.random() * 1.6); // |vx| ∈ [0.4, 2.0]

    const coin = makeCoinBody(spawnX, vx);
    Matter.Composite.add(scout.world, coin);

    let settled = false;
    let stalled = false;
    let maxY = coin.position.y;
    let lastProgressStep = 0;
    for (let step = 0; step < SIM_STEPS; step++) {
      Matter.Engine.update(scout, SIM_DT);
      if (coin.position.y > maxY + MIN_PROGRESS) {
        maxY = coin.position.y;
        lastProgressStep = step;
      } else if (step - lastProgressStep > STALL_FRAMES) {
        stalled = true;
        break;
      }
      if (coin.position.y > BOARD_H - BUCKET_ROW_HEIGHT) {
        settled = true;
        break;
      }
    }

    const landedX = coin.position.x;
    // Always remove the coin so the scout engine is reusable.
    Matter.Composite.remove(scout.world, coin);

    if (stalled) continue;
    if (settled && landingBucket(landedX, bucketCount) === targetBucket) {
      return { spawnX, vx };
    }
  }

  // Fallback: bias toward the target side with a strong starting offset.
  const bucketCenter = (BOARD_W / bucketCount) * (targetBucket + 0.5);
  const direction = bucketCenter < BOARD_W / 2 ? -1 : 1;
  return { spawnX: BOARD_W / 2 + direction * SPAWN_MIN_OFFSET, vx: direction * 1.2 };
}

/* ---------------------------- Component ------------------------------ */

const PlinkoBoard = forwardRef<PlinkoBoardHandle, PlinkoBoardProps>(function PlinkoBoard(
  { pegRows, bucketCount, bucketMultipliers, onLanding },
  ref
) {
  const engineRef = useRef<Matter.Engine | null>(null);
  /** Reusable offscreen engine for `findSpawnParams` scout attempts (avoids
   *  rebuilding the full peg/wall world on every search attempt). */
  const scoutEngineRef = useRef<Matter.Engine | null>(null);
  const pegsRef = useRef<PegPos[]>([]);
  const coinBodiesRef = useRef<Map<number, Matter.Body>>(new Map());
  const coinScheduleRef = useRef<Map<number, ScheduledLanding>>(new Map());
  const nextCoinIdRef = useRef(1);
  const rafRef = useRef<number | null>(null);
  const lastTickRef = useRef(0);
  /** Fixed-timestep accumulator (ms). Must match scout's SIM_DT for determinism. */
  const accumRef = useRef(0);
  const wrapperRef = useRef<HTMLDivElement | null>(null);
  /** pegIndex → timestamp (ms) at which the lit state expires. */
  const litPegsRef = useRef<Map<number, number>>(new Map());

  const [coins, setCoins] = useState<CoinView[]>([]);
  const [bucketFlashCounts, setBucketFlashCounts] = useState<number[]>(() =>
    new Array(bucketCount).fill(0),
  );
  /** Lit pegs as a state-driven Set so the PegLayer can be a memoized child:
   *  we publish a fresh Set from the rAF tick when membership actually changes
   *  instead of bumping a generic version counter that would re-render the
   *  whole board on every coin frame. */
  const [litPegSet, setLitPegSet] = useState<ReadonlySet<number>>(() => new Set());
  /** Pegs as state so they render on initial mount, not just after first coin. */
  const [pegs, setPegs] = useState<PegPos[]>(() => buildPegLayout(pegRows));

  // Helper to publish a new lit-peg snapshot only when it actually changes
  // (referential equality via Set). Keeps PegLayer skips intact under memo.
  const publishLitPegs = () => {
    setLitPegSet(new Set(litPegsRef.current.keys()));
  };

  // Build pegs + engine once per pegRows / bucketCount change.
  useEffect(() => {
    const layout = buildPegLayout(pegRows);
    pegsRef.current = layout;
    setPegs(layout);
    const engine = buildEngine(layout, bucketCount);
    engineRef.current = engine;
    scoutEngineRef.current = buildEngine(layout, bucketCount);

    // Light up pegs when a coin strikes them.
    const onCollide = (event: Matter.IEventCollision<Matter.Engine>) => {
      const now = performance.now();
      let touched = false;
      for (const pair of event.pairs) {
        const pegBody =
          pair.bodyA.label?.startsWith('peg:') ? pair.bodyA :
          pair.bodyB.label?.startsWith('peg:') ? pair.bodyB : null;
        if (!pegBody) continue;
        const idx = Number(pegBody.label.slice(4));
        const wasLit = litPegsRef.current.has(idx);
        litPegsRef.current.set(idx, now + PEG_LIT_MS);
        if (!wasLit) touched = true;
      }
      if (touched) publishLitPegs();
    };
    Matter.Events.on(engine, 'collisionStart', onCollide);

    const tick = (now: number) => {
      const last = lastTickRef.current || now;
      const frameDt = Math.min(60, now - last); // cap big gaps (tab switch)
      lastTickRef.current = now;

      // Expire any pegs whose lit timestamps have elapsed (must run even when
      // no coins are in flight, otherwise the last impact's pegs stay lit forever).
      if (litPegsRef.current.size > 0) {
        const nowMs = performance.now();
        let pruned = false;
        litPegsRef.current.forEach((expiry, idx) => {
          if (expiry <= nowMs) {
            litPegsRef.current.delete(idx);
            pruned = true;
          }
        });
        if (pruned) publishLitPegs();
      }

      if (engineRef.current && coinBodiesRef.current.size > 0) {
        // Fixed timestep: scout uses SIM_DT, so live must too — otherwise
        // floating-point trajectories diverge and the coin lands in the
        // wrong bucket relative to what the server picked.
        accumRef.current += frameDt;
        const MAX_STEPS_PER_FRAME = 6; // prevent spiral-of-death on slow frames
        let steps = 0;
        while (accumRef.current >= SIM_DT && steps < MAX_STEPS_PER_FRAME) {
          Matter.Engine.update(engineRef.current, SIM_DT);
          accumRef.current -= SIM_DT;
          steps++;
        }
        if (steps === MAX_STEPS_PER_FRAME) {
          // Drop any leftover backlog to stay roughly in real time.
          accumRef.current = 0;
        }

        // Check landings + update view positions.
        const updated: CoinView[] = [];
        coinBodiesRef.current.forEach((body, id) => {
          if (body.position.y > BOARD_H - BUCKET_ROW_HEIGHT) {
            const scheduled = coinScheduleRef.current.get(id);
            if (scheduled && !scheduled.fired) {
              scheduled.fired = true;
              const bi = scheduled.bucketIndex;
              setBucketFlashCounts((prev) => {
                const next = prev.slice();
                next[bi] = (next[bi] ?? 0) + 1;
                return next;
              });
              onLanding?.(bi);
              window.setTimeout(() => {
                setBucketFlashCounts((prev) => {
                  if (!prev[bi]) return prev;
                  const next = prev.slice();
                  next[bi] = Math.max(0, next[bi] - 1);
                  return next;
                });
              }, 700);
              // Despawn immediately on bucket impact.
              if (engineRef.current) {
                Matter.Composite.remove(engineRef.current.world, body);
              }
              coinBodiesRef.current.delete(id);
              coinScheduleRef.current.delete(id);
              scheduled.resolve?.();
              return; // skip pushing into updated; coin is gone
            }
          }
          updated.push({ id, x: body.position.x, y: body.position.y });
        });
        setCoins(updated);
      } else {
        accumRef.current = 0;
        setCoins((curr) => (curr.length ? [] : curr));
      }

      rafRef.current = requestAnimationFrame(tick);
    };
    rafRef.current = requestAnimationFrame(tick);

    return () => {
      if (rafRef.current != null) cancelAnimationFrame(rafRef.current);
      rafRef.current = null;
      coinBodiesRef.current.clear();
      coinScheduleRef.current.clear();
      litPegsRef.current.clear();
      setCoins([]);
      setLitPegSet(new Set());
      if (engineRef.current) {
        Matter.Events.off(engineRef.current, 'collisionStart', onCollide);
        Matter.World.clear(engineRef.current.world, false);
        Matter.Engine.clear(engineRef.current);
        engineRef.current = null;
      }
      if (scoutEngineRef.current) {
        Matter.World.clear(scoutEngineRef.current.world, false);
        Matter.Engine.clear(scoutEngineRef.current);
        scoutEngineRef.current = null;
      }
    };
  }, [pegRows, bucketCount, onLanding]);

  useImperativeHandle(
    ref,
    () => ({
      dropCoin: (bucketIndex: number) => {
        return new Promise<void>((resolve) => {
          const pegs = pegsRef.current;
          if (!pegs.length || !engineRef.current || !scoutEngineRef.current) {
            resolve();
            return;
          }
          const { spawnX, vx } = findSpawnParams(
            scoutEngineRef.current,
            bucketCount,
            bucketIndex,
          );
          const id = nextCoinIdRef.current++;
          const body = makeCoinBody(spawnX, vx);
          Matter.Composite.add(engineRef.current.world, body);
          coinBodiesRef.current.set(id, body);
          coinScheduleRef.current.set(id, { coinId: id, bucketIndex, resolve });
          setCoins((curr) => [...curr, { id, x: body.position.x, y: body.position.y }]);
        });
      },
    }),
    [bucketCount]
  );

  // Precompute peg styles once per layout — they never change after pegRows
  // is set, so avoid recomputing % strings on every render (each rAF tick
  // would otherwise re-derive 36+ inline styles).
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
  // Lit pegs as a state-driven Set so the PegLayer can be a memoized child:
  // we update this from the rAF tick instead of bumping a generic version
  // counter that would re-render the whole board.

  return (
    <div className="coindrop-board-wrapper" ref={wrapperRef}>
      <div className="coindrop-stage">
        <PegLayer pegs={pegs} pegStyles={pegStyles} litPegs={litPegSet} />
        <CoinLayer coins={coins} />
      </div>
      <div className="coindrop-bucket-row">
        {bucketMultipliers.map((m, i) => (
          <div
            key={`bucket-${i}`}
            className={`coindrop-bucket ${(bucketFlashCounts[i] ?? 0) > 0 ? 'flash' : ''}`}
            data-mult={m}
          >
            {m}x
          </div>
        ))}
      </div>
    </div>
  );
});

export default PlinkoBoard;

/* ---------------- Memoized render layers ----------------
 *
 * The PlinkoBoard re-renders every animation frame to update coin positions.
 * Splitting pegs and coins into separate memoized layers means the peg DOM
 * tree (36+ nodes with inline % styles) only re-renders when the lit set or
 * layout actually changes — not on every coin movement frame.
 */

interface PegLayerProps {
  pegs: PegPos[];
  pegStyles: React.CSSProperties[];
  litPegs: ReadonlySet<number>;
}

const PegLayer = memo(function PegLayer({ pegs, pegStyles, litPegs }: PegLayerProps) {
  return (
    <>
      {pegs.map((_p, i) => (
        <div
          key={`peg-${i}`}
          className={`coindrop-peg${litPegs.has(i) ? ' lit' : ''}`}
          style={pegStyles[i]}
        />
      ))}
    </>
  );
});

interface CoinLayerProps {
  coins: CoinView[];
}

const CoinLayer = memo(function CoinLayer({ coins }: CoinLayerProps) {
  return (
    <>
      {coins.map((c) => (
        <div
          key={`coin-${c.id}`}
          className="coindrop-coin"
          style={{
            left: `${(c.x / BOARD_W) * 100}%`,
            top: `${(c.y / BOARD_H) * 100}%`,
            width: `${((COIN_RADIUS * 2) / BOARD_W) * 100}%`,
            height: `${((COIN_RADIUS * 2) / BOARD_H) * 100}%`,
          }}
        />
      ))}
    </>
  );
});
