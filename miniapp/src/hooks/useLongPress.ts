import { useRef, useCallback } from 'react';

interface UseLongPressOptions {
  onLongPress: () => void;
  onPress?: () => void;
  delay?: number;
}

interface UseLongPressResult {
  onTouchStart: (e: React.TouchEvent) => void;
  onTouchEnd: () => void;
  onTouchMove: (e: React.TouchEvent) => void;
}

/**
 * Hook to detect long press on touch devices.
 * Triggers onLongPress after holding for the specified delay.
 * If released before delay, triggers onPress (if provided).
 */
export function useLongPress({
  onLongPress,
  onPress,
  delay = 500,
}: UseLongPressOptions): UseLongPressResult {
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const isLongPressRef = useRef(false);
  const startPosRef = useRef<{ x: number; y: number } | null>(null);

  const clear = useCallback(() => {
    if (timerRef.current) {
      clearTimeout(timerRef.current);
      timerRef.current = null;
    }
  }, []);

  const onTouchStart = useCallback(
    (e: React.TouchEvent) => {
      isLongPressRef.current = false;
      
      // Store the starting position
      const touch = e.touches[0];
      startPosRef.current = { x: touch.clientX, y: touch.clientY };

      timerRef.current = setTimeout(() => {
        isLongPressRef.current = true;
        onLongPress();
      }, delay);
    },
    [onLongPress, delay]
  );

  const onTouchEnd = useCallback(
    () => {
      if (!isLongPressRef.current && onPress) {
        onPress();
      }
      clear();
      startPosRef.current = null;
    },
    [onPress, clear]
  );

  const onTouchMove = useCallback(
    (e: React.TouchEvent) => {
      // Cancel long press if finger moves too far (scrolling)
      if (startPosRef.current) {
        const touch = e.touches[0];
        const dx = Math.abs(touch.clientX - startPosRef.current.x);
        const dy = Math.abs(touch.clientY - startPosRef.current.y);
        const moveThreshold = 10; // pixels
        
        if (dx > moveThreshold || dy > moveThreshold) {
          clear();
        }
      }
    },
    [clear]
  );

  return {
    onTouchStart,
    onTouchEnd,
    onTouchMove,
  };
}

export default useLongPress;
