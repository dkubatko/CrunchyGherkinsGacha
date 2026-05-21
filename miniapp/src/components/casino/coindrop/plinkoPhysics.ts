/**
 * plinkoPhysics — pure, framework-free Plinko physics simulation.
 *
 * This module contains all Matter.js scout/recording logic, with no React or
 * DOM dependencies. It is imported by both:
 *   - the main thread (as a crash-recovery fallback for the worker)
 *   - the Web Worker (plinkoPath.worker.ts) — primary execution path
 *
 * See PlinkoBoard.tsx for the record-and-replay design rationale.
 */
import Matter from 'matter-js';

export const BOARD_W = 380;
export const BOARD_H = 460;
export const PEG_RADIUS = 5;
export const COIN_RADIUS = 12;
export const BUCKET_ROW_HEIGHT = 52;
export const TOP_MARGIN = 36;
export const SIDE_MARGIN = 26;
export const BOTTOM_PEG_MARGIN = BUCKET_ROW_HEIGHT + 30;

const COIN_NON_COLLIDING_GROUP = -1; // negative group = never collide with same group

export interface PegPos {
  x: number;
  y: number;
}

export interface PegHit {
  pegIndex: number;
  /** Substep index (1-based; matches frames sampled AFTER Engine.update). */
  frame: number;
}

/**
 * A recorded coin trajectory. `frames` packs [x, y, angle] per substep,
 * length = (landedFrame + 1) * 3 (frame 0 is the spawn snapshot).
 */
export interface RecordedPath {
  frames: Float32Array;
  landedFrame: number;
  pegHits: PegHit[];
  bucketIndex: number;
}

/* --------------------------- Peg layout ------------------------------ */

/**
 * Pyramid (classic Plinko / Galton) layout: row r has r+1 pegs.
 * See PlinkoBoard for full description.
 */
export function buildPegLayout(rows: number): PegPos[] {
  const usableHeight = BOARD_H - TOP_MARGIN - BOTTOM_PEG_MARGIN;
  const rowSpacing = usableHeight / Math.max(1, rows - 1);
  const usableWidth = BOARD_W - SIDE_MARGIN * 2;
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

export function buildEngine(pegs: PegPos[], bucketCount: number): Matter.Engine {
  const engine = Matter.Engine.create({
    gravity: { x: 0, y: 1, scale: 0.0014 },
  });

  const wallOpts = { isStatic: true, restitution: 0.05, friction: 0.4 };
  const walls = [
    Matter.Bodies.rectangle(-10, BOARD_H / 2, 20, BOARD_H, wallOpts),
    Matter.Bodies.rectangle(BOARD_W + 10, BOARD_H / 2, 20, BOARD_H, wallOpts),
    Matter.Bodies.rectangle(BOARD_W / 2, BOARD_H + 10, BOARD_W, 20, wallOpts),
  ];
  Matter.Composite.add(engine.world, walls);

  const pegBodies = pegs.map((p, i) =>
    Matter.Bodies.circle(p.x, p.y, PEG_RADIUS, {
      isStatic: true,
      restitution: 0.65,
      friction: 0.05,
      label: `peg:${i}`,
    })
  );
  Matter.Composite.add(engine.world, pegBodies);

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

const SPAWN_Y = -COIN_RADIUS * 2;

export function makeCoinBody(x: number, vx: number): Matter.Body {
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

export function landingBucket(x: number, bucketCount: number): number {
  const idx = Math.floor((x / BOARD_W) * bucketCount);
  return Math.max(0, Math.min(bucketCount - 1, idx));
}

/* --------------- Offline path recording (deterministic) -------------- */

const MAX_SEARCH_ATTEMPTS = 200;
export const SIM_STEPS = 600;
export const SIM_DT = 1000 / 60;
const STALL_FRAMES = 18;
const MIN_PROGRESS = 1.5;
const SPAWN_MIN_OFFSET = 2;
const SPAWN_MAX_OFFSET = 8;

/**
 * Build a fresh scout engine, search for (spawnX, vx) that lands a coin in
 * `targetBucket`, and return the full recorded trajectory of the winning
 * attempt — which the on-screen animation then replays.
 */
export function recordPath(
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

  const scratchBuffer = new Float32Array((SIM_STEPS + 1) * 3);

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

    if (landedFrame < 0) return null;
    if (landingBucket(finalX, bucketCount) !== targetBucket) return null;

    return {
      frames: scratchBuffer.slice(0, bufIdx),
      landedFrame,
      pegHits: recordingPegHits.slice(),
      bucketIndex: targetBucket,
    };
  };

  // Search for (spawnX, vx) that lands in targetBucket. First MAX_SEARCH_ATTEMPTS
  // tries are fully random (fast path — succeeds ~always for interior buckets).
  // Beyond that, we bias half the attempts toward the target side to converge
  // faster on hard edge buckets. PANIC_CAP is a sanity net against pathological
  // configurations (effectively unreachable with dividers in place); on the
  // astronomically unlikely chance it trips, fall through to the synthetic
  // free-fall below.
  const bucketCenter = (BOARD_W / bucketCount) * (targetBucket + 0.5);
  const direction = bucketCenter < BOARD_W / 2 ? -1 : 1;
  const PANIC_CAP = 10000;

  for (let attempt = 0; attempt < PANIC_CAP; attempt++) {
    const biasTarget = attempt >= MAX_SEARCH_ATTEMPTS && Math.random() < 0.5;
    const offsetSign = biasTarget ? direction : (Math.random() < 0.5 ? -1 : 1);
    const spawnX =
      BOARD_W / 2 +
      offsetSign * (SPAWN_MIN_OFFSET + Math.random() * (SPAWN_MAX_OFFSET - SPAWN_MIN_OFFSET));
    const vxSign = biasTarget ? direction : (Math.random() < 0.5 ? -1 : 1);
    const vx = vxSign * (0.4 + Math.random() * 1.6);

    const path = tryAttempt(spawnX, vx);
    if (path) {
      cleanup();
      return path;
    }
  }
  cleanup();

  // Synthetic last-resort path: free-fall animation from board top to the
  // target bucket center. Produces a smooth ~700ms drop instead of a 2-frame
  // teleport, so the rare case where scout exhausts all attempts + biased
  // fallback still looks like a real drop to the user. Trajectory is a
  // simple parabola with constant downward acceleration; no peg interaction
  // (pegHits stays empty — won't light any pegs, but the user won't notice
  // versus the misalignment they'd see otherwise).
  const cx = (BOARD_W / bucketCount) * (targetBucket + 0.5);
  const startX = BOARD_W / 2;
  const startY = -COIN_RADIUS * 2;
  const endY = BOARD_H - BUCKET_ROW_HEIGHT + 1;
  const FALLBACK_FRAMES = 42; // ~700ms at 60fps
  const fallbackFrames = new Float32Array((FALLBACK_FRAMES + 1) * 3);
  for (let i = 0; i <= FALLBACK_FRAMES; i++) {
    const t = i / FALLBACK_FRAMES;
    // Quadratic (gravity-like) easing on Y; linear on X toward target.
    const y = startY + (endY - startY) * (t * t);
    const x = startX + (cx - startX) * t;
    const angle = t * Math.PI * 2; // one rotation across the fall
    fallbackFrames[i * 3] = x;
    fallbackFrames[i * 3 + 1] = y;
    fallbackFrames[i * 3 + 2] = angle;
  }
  return {
    frames: fallbackFrames,
    landedFrame: FALLBACK_FRAMES,
    pegHits: [],
    bucketIndex: targetBucket,
  };
}
