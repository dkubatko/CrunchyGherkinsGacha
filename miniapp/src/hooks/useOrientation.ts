import { useState, useEffect } from 'react';
import type { OrientationData } from '../types';
import { TelegramUtils } from '../utils/telegram';

interface UseOrientationResult {
  orientation: OrientationData;
  orientationKey: number;
  resetTiltReference: () => void;
}

export const useOrientation = (): UseOrientationResult => {
  const [orientation, setOrientation] = useState<OrientationData>({
    alpha: 0,
    beta: 0,
    gamma: 0,
    isStarted: false
  });
  const [orientationKey, setOrientationKey] = useState(0);

  const resetTiltReference = () => {
    setOrientationKey(prev => prev + 1);
  };

  useEffect(() => {
    const cleanup = TelegramUtils.startOrientationTracking(setOrientation);
    return cleanup;
  }, []);

  return {
    orientation,
    orientationKey,
    resetTiltReference
  };
};