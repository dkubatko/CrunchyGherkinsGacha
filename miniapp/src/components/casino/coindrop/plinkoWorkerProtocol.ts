/**
 * Message protocol shared between PlinkoBoard (main thread) and
 * plinkoPath.worker.ts (worker thread).
 */
import type { PegPos, PegHit } from './plinkoPhysics';

export interface PlinkoRequestMsg {
  type: 'compute';
  id: number;
  pegs: PegPos[];
  bucketCount: number;
  targetBucket: number;
}

export interface PlinkoResponseMsg {
  type: 'result';
  id: number;
  frames: Float32Array;
  landedFrame: number;
  pegHits: PegHit[];
  bucketIndex: number;
}
