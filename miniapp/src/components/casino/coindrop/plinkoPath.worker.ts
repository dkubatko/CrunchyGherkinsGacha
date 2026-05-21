/**
 * plinkoPath.worker — runs `recordPath` (Matter.js scout) off the main thread.
 *
 * See PlinkoBoard.tsx for why this is a worker (avoids blocking the main
 * thread for 50–200ms per drop, which would defer the previous coin's
 * rAF landing event and produce a "replayed glow/haptic" perception).
 */
import { recordPath } from './plinkoPhysics';
import type { PlinkoRequestMsg, PlinkoResponseMsg } from './plinkoWorkerProtocol';

self.onmessage = (e: MessageEvent<PlinkoRequestMsg>) => {
  const msg = e.data;
  if (!msg || msg.type !== 'compute') return;

  const { id, pegs, bucketCount, targetBucket } = msg;
  const path = recordPath(pegs, bucketCount, targetBucket);

  const response: PlinkoResponseMsg = {
    type: 'result',
    id,
    frames: path.frames,
    landedFrame: path.landedFrame,
    pegHits: path.pegHits,
    bucketIndex: path.bucketIndex,
  };

  // Transfer the trajectory buffer (zero-copy).
  (self as unknown as Worker).postMessage(response, [path.frames.buffer]);
};
