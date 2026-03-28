import { useState, useEffect, useCallback } from 'react';
import type { OrientationData } from '../types';
import { TelegramUtils } from '../utils/telegram';

interface UseOrientationResult {
  orientation: OrientationData;
  orientationKey: number;
  resetTiltReference: () => void;
}

interface UseOrientationOptions {
  enabled?: boolean;
}

// Singleton tracking state — ensures only one DeviceOrientation.start() call
// regardless of how many hook instances are active (e.g. CollectionTab + AspectsTab).
type OrientationCallback = (data: OrientationData) => void;
let sharedCleanup: (() => void) | null = null;
const subscribers = new Set<OrientationCallback>();

function subscribeOrientation(callback: OrientationCallback): () => void {
  subscribers.add(callback);

  if (!sharedCleanup) {
    sharedCleanup = TelegramUtils.startOrientationTracking((data) => {
      for (const cb of subscribers) cb(data);
    });
  }

  return () => {
    subscribers.delete(callback);
    if (subscribers.size === 0 && sharedCleanup) {
      sharedCleanup();
      sharedCleanup = null;
    }
  };
}

export const useOrientation = (options: UseOrientationOptions = {}): UseOrientationResult => {
  const { enabled = true } = options;
  const [orientation, setOrientation] = useState<OrientationData>({
    alpha: 0,
    beta: 0,
    gamma: 0,
    isStarted: false
  });
  const [orientationKey, setOrientationKey] = useState(0);

  const resetTiltReference = useCallback(() => {
    setOrientationKey(prev => prev + 1);
  }, []);

  useEffect(() => {
    if (!enabled) return;
    return subscribeOrientation(setOrientation);
  }, [enabled]);

  return {
    orientation,
    orientationKey,
    resetTiltReference
  };
};