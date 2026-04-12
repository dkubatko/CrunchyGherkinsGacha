import { useRef, useState, useCallback, useEffect } from 'react';
import { TelegramUtils } from '@/utils/telegram';

const THRESHOLD = 64;
const MAX_PULL = 80;
const RESISTANCE = 0.35;
const SNAP_DURATION = 300;
const MIN_REFRESH_DURATION = 500;
const DIRECTION_LOCK_THRESHOLD = 10;
const SPIN_SPEED = 6; // degrees per frame during refresh
const REFRESH_HOLD_HEIGHT = 40; // gap height to hold during refresh (fits spinner + padding)

export interface UsePullToRefreshReturn {
  pullDistance: number;
  isRefreshing: boolean;
  spinnerAngle: number;
}

export const usePullToRefresh = (
  scrollRef: React.RefObject<HTMLElement | null>,
  onRefresh: (() => Promise<void>) | undefined,
  enabled = true,
): UsePullToRefreshReturn => {
  const [pullDistance, setPullDistance] = useState(0);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [spinnerAngle, setSpinnerAngle] = useState(0);

  // Refs for gesture tracking (avoid re-renders during drag)
  const pulling = useRef(false);
  const startY = useRef(0);
  const startScrollTop = useRef(0);
  const currentPull = useRef(0);
  const directionLocked = useRef<'vertical' | 'horizontal' | null>(null);
  const startX = useRef(0);
  const refreshingRef = useRef(false);
  const mountedRef = useRef(true);
  const angleRef = useRef(0);
  const rafId = useRef(0);
  const snapRafId = useRef(0);
  // Mouse-specific: track whether the button is held during the gesture
  const mouseDown = useRef(false);
  const thresholdCrossed = useRef(false);

  const computePull = (deltaY: number): number => {
    const raw = deltaY * RESISTANCE;
    return Math.min(Math.max(0, raw), MAX_PULL);
  };

  const computeAngle = (pull: number): number => {
    return (pull / THRESHOLD) * 360;
  };

  const updatePullWithHaptic = useCallback((pull: number) => {
    currentPull.current = pull;
    setPullDistance(pull);
    angleRef.current = computeAngle(pull);
    setSpinnerAngle(angleRef.current);

    if (pull >= THRESHOLD && !thresholdCrossed.current) {
      thresholdCrossed.current = true;
      TelegramUtils.triggerHapticImpact('light');
    } else if (pull < THRESHOLD && thresholdCrossed.current) {
      thresholdCrossed.current = false;
    }
  }, []);

  const resetPullState = () => {
    currentPull.current = 0;
    angleRef.current = 0;
    thresholdCrossed.current = false;
    setPullDistance(0);
    setSpinnerAngle(0);
  };

  // Animate spinner during refresh
  const startSpinAnimation = useCallback(() => {
    const spin = () => {
      if (!refreshingRef.current || !mountedRef.current) return;
      angleRef.current = (angleRef.current + SPIN_SPEED) % 360;
      setSpinnerAngle(angleRef.current);
      rafId.current = requestAnimationFrame(spin);
    };
    rafId.current = requestAnimationFrame(spin);
  }, []);

  // Animate to a target pull distance
  const animateSnapTo = useCallback((from: number, to: number, onDone?: () => void) => {
    const startTime = performance.now();
    const distance = from - to;
    const animate = (now: number) => {
      if (!mountedRef.current) return;
      const elapsed = now - startTime;
      const progress = Math.min(elapsed / SNAP_DURATION, 1);
      // easeOut cubic
      const eased = 1 - Math.pow(1 - progress, 3);
      const value = from - distance * eased;
      currentPull.current = value;
      setPullDistance(value);
      if (progress < 1) {
        snapRafId.current = requestAnimationFrame(animate);
      } else {
        currentPull.current = to;
        setPullDistance(to);
        onDone?.();
      }
    };
    snapRafId.current = requestAnimationFrame(animate);
  }, []);

  const finishRefresh = useCallback(() => {
    if (!mountedRef.current) return;
    refreshingRef.current = false;
    cancelAnimationFrame(rafId.current);
    setIsRefreshing(false);
    animateSnapTo(currentPull.current, 0, () => {
      angleRef.current = 0;
      setSpinnerAngle(0);
    });
  }, [animateSnapTo]);

  const handlePullRelease = useCallback(() => {
    if (!pulling.current) return;
    pulling.current = false;
    directionLocked.current = null;

    if (currentPull.current >= THRESHOLD && onRefresh && !refreshingRef.current) {
      refreshingRef.current = true;
      setIsRefreshing(true);
      TelegramUtils.triggerHapticImpact('medium');
      startSpinAnimation();
      // Snap gap down to hold height, then start refresh
      animateSnapTo(currentPull.current, REFRESH_HOLD_HEIGHT, () => {
        const start = performance.now();
        const ensureMinDuration = () => {
          const elapsed = performance.now() - start;
          const remaining = MIN_REFRESH_DURATION - elapsed;
          if (remaining > 0) {
            return new Promise<void>(r => setTimeout(r, remaining));
          }
          return Promise.resolve();
        };
        onRefresh()
          .then(ensureMinDuration, ensureMinDuration)
          .then(() => {
            TelegramUtils.triggerHapticImpact('light');
            finishRefresh();
          });
      });
    } else if (!refreshingRef.current) {
      animateSnapTo(currentPull.current, 0, () => {
        angleRef.current = 0;
        setSpinnerAngle(0);
      });
    }
  }, [onRefresh, startSpinAnimation, finishRefresh, animateSnapTo]);

  useEffect(() => {
    mountedRef.current = true;
    const el = scrollRef.current;
    if (!el || !enabled || !onRefresh) return;

    // --- Touch events (mobile) ---
    const onTouchStart = (e: TouchEvent) => {
      if (refreshingRef.current) return;
      cancelAnimationFrame(snapRafId.current);
      resetPullState();
      const touch = e.touches[0];
      startY.current = touch.clientY;
      startX.current = touch.clientX;
      startScrollTop.current = el.scrollTop;
      directionLocked.current = null;
      if (el.scrollTop <= 0) {
        pulling.current = true;
      }
    };

    const onTouchMove = (e: TouchEvent) => {
      if (!pulling.current || refreshingRef.current) return;
      const touch = e.touches[0];
      const deltaY = touch.clientY - startY.current;
      const deltaX = touch.clientX - startX.current;

      // Prevent native overscroll immediately when at top and pulling down.
      // Must fire BEFORE direction lock — iOS starts rubber-band bounce on the
      // first touchmove frame if we don't block it.
      if (deltaY > 0 && el.scrollTop <= 0) {
        e.preventDefault();
      }

      // Direction locking
      if (!directionLocked.current) {
        const absX = Math.abs(deltaX);
        const absY = Math.abs(deltaY);
        if (absX > DIRECTION_LOCK_THRESHOLD || absY > DIRECTION_LOCK_THRESHOLD) {
          directionLocked.current = absX > absY ? 'horizontal' : 'vertical';
          if (directionLocked.current === 'horizontal') {
            pulling.current = false;
            return;
          }
        } else {
          return; // Wait for enough movement to determine direction
        }
      }

      if (deltaY <= 0) {
        // Pushing up - reset pull
        if (currentPull.current > 0) resetPullState();
        return;
      }

      const pull = computePull(deltaY);
      updatePullWithHaptic(pull);
    };

    const onTouchEnd = () => {
      handlePullRelease();
    };

    const onTouchCancel = () => {
      if (pulling.current) {
        pulling.current = false;
        directionLocked.current = null;
        if (!refreshingRef.current) {
          animateSnapTo(currentPull.current, 0, () => {
            angleRef.current = 0;
            setSpinnerAngle(0);
          });
        }
      }
    };

    // --- Mouse events (desktop) ---
    const onMouseDown = (e: MouseEvent) => {
      if (refreshingRef.current || e.button !== 0) return;
      cancelAnimationFrame(snapRafId.current);
      resetPullState();
      startY.current = e.clientY;
      startX.current = e.clientX;
      startScrollTop.current = el.scrollTop;
      directionLocked.current = null;
      mouseDown.current = true;
      if (el.scrollTop <= 0) {
        pulling.current = true;
      }
    };

    const onMouseMove = (e: MouseEvent) => {
      if (!mouseDown.current || !pulling.current || refreshingRef.current) return;
      const deltaY = e.clientY - startY.current;
      const deltaX = e.clientX - startX.current;

      // Direction locking
      if (!directionLocked.current) {
        const absX = Math.abs(deltaX);
        const absY = Math.abs(deltaY);
        if (absX > DIRECTION_LOCK_THRESHOLD || absY > DIRECTION_LOCK_THRESHOLD) {
          directionLocked.current = absX > absY ? 'horizontal' : 'vertical';
          if (directionLocked.current === 'horizontal') {
            pulling.current = false;
            return;
          }
        } else {
          return;
        }
      }

      if (deltaY <= 0) {
        if (currentPull.current > 0) resetPullState();
        return;
      }

      const pull = computePull(deltaY);
      updatePullWithHaptic(pull);

      // Prevent text selection during drag
      e.preventDefault();
    };

    const onMouseUp = () => {
      if (!mouseDown.current) return;
      mouseDown.current = false;
      handlePullRelease();
    };

    el.addEventListener('touchstart', onTouchStart, { passive: true });
    // Non-passive to allow preventDefault during active pull (prevents native overscroll)
    el.addEventListener('touchmove', onTouchMove, { passive: false });
    el.addEventListener('touchend', onTouchEnd, { passive: true });
    el.addEventListener('touchcancel', onTouchCancel, { passive: true });
    el.addEventListener('mousedown', onMouseDown);
    window.addEventListener('mousemove', onMouseMove);
    window.addEventListener('mouseup', onMouseUp);

    return () => {
      mountedRef.current = false;
      el.removeEventListener('touchstart', onTouchStart);
      el.removeEventListener('touchmove', onTouchMove);
      el.removeEventListener('touchend', onTouchEnd);
      el.removeEventListener('touchcancel', onTouchCancel);
      el.removeEventListener('mousedown', onMouseDown);
      window.removeEventListener('mousemove', onMouseMove);
      window.removeEventListener('mouseup', onMouseUp);
      cancelAnimationFrame(rafId.current);
      cancelAnimationFrame(snapRafId.current);
    };
  }, [scrollRef, enabled, onRefresh, handlePullRelease, animateSnapTo, updatePullWithHaptic]);

  return { pullDistance, isRefreshing, spinnerAngle };
};
