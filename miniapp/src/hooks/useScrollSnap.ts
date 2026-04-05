import { useRef, useState, useCallback, useEffect } from 'react';

interface UseScrollSnapOptions {
  paneCount: number;
  initialIndex?: number;
  locked?: boolean;
  /** Called with continuous progress (0..N-1) for direct DOM indicator updates. */
  onProgress?: (progress: number) => void;
}

interface UseScrollSnapResult {
  containerRef: React.RefObject<HTMLDivElement | null>;
  activeIndex: number;
  goTo: (index: number) => void;
}

// CSS transition duration (ms) — keep in sync with SwipeableSubTabs.css
const TRANSITION_MS = 300;

// Cubic-bezier(0.25, 1, 0.5, 1) approximation for JS interpolation
const easeOutQuart = (t: number) => 1 - (1 - t) ** 4;

/**
 * Hook for swipeable horizontal pane navigation using CSS transforms.
 *
 * Panes are positioned via `translateX()` on the track element (GPU-composited).
 * `touch-action: pan-y` on the track delegates vertical scrolling to the browser
 * while JS handles horizontal gestures. Each touch resets completely — no stickiness.
 */
export const useScrollSnap = ({
  paneCount,
  initialIndex = 0,
  locked = false,
  onProgress,
}: UseScrollSnapOptions): UseScrollSnapResult => {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const [activeIndex, setActiveIndex] = useState(initialIndex);
  const indexRef = useRef(initialIndex);

  const onProgressRef = useRef(onProgress);
  onProgressRef.current = onProgress;
  const emitProgress = useCallback((p: number) => {
    onProgressRef.current?.(p);
  }, []);

  // Snap-animation rAF handle (cancelled on new gesture or unmount)
  const snapRafRef = useRef(0);
  const cancelSnapRaf = useCallback(() => {
    if (snapRafRef.current) {
      cancelAnimationFrame(snapRafRef.current);
      snapRafRef.current = 0;
    }
  }, []);

  // Track whether a gesture is active (shared across touch/mouse via ref)
  const gestureActiveRef = useRef(false);

  // ── helpers ──

  const getWidth = () => containerRef.current?.clientWidth ?? 0;

  const clampOffset = useCallback(
    (raw: number) => {
      const maxRight = 0;
      const maxLeft = -(paneCount - 1) * getWidth();
      return Math.max(maxLeft, Math.min(maxRight, raw));
    },
    [paneCount],
  );

  /** Check if a horizontal drag direction has a valid neighbor pane. */
  const hasNeighbor = useCallback(
    (dx: number): boolean => {
      const idx = indexRef.current;
      // dx < 0 = dragging left = moving toward higher index
      if (dx < 0) return idx < paneCount - 1;
      // dx > 0 = dragging right = moving toward lower index
      if (dx > 0) return idx > 0;
      return false;
    },
    [paneCount],
  );

  /** Determine snap target from progress relative to the base index. */
  const computeTarget = (
    currentProg: number,
    base: number,
    velocity: number,
    velocityThreshold: number,
    snapRatio: number,
  ): number => {
    if (Math.abs(velocity) > velocityThreshold) {
      return velocity < 0 ? base + 1 : base - 1;
    }
    // Symmetric threshold around the base index
    if (currentProg > base + snapRatio) return base + 1;
    if (currentProg < base - snapRatio) return base - 1;
    return base;
  };

  /**
   * Snap to targetIndex with CSS transition.
   * Animates progress via JS interpolation (no getComputedStyle per frame).
   */
  const snapTo = useCallback(
    (targetIndex: number) => {
      const el = containerRef.current;
      if (!el) return;
      const clamped = Math.max(0, Math.min(targetIndex, paneCount - 1));
      indexRef.current = clamped;
      setActiveIndex(clamped);

      el.classList.remove('dragging');
      const w = getWidth();
      const targetPx = -clamped * w;

      // Capture start progress before applying the target transform
      const startProg = w > 0
        ? Math.max(0, Math.min(paneCount - 1, -new DOMMatrixReadOnly(getComputedStyle(el).transform).m41 / w))
        : clamped;

      el.style.transform = `translateX(${targetPx}px)`;

      // Interpolate indicator progress over the transition duration
      cancelSnapRaf();
      const startTime = performance.now();
      const endProg = clamped;

      if (Math.abs(startProg - endProg) < 0.002) {
        emitProgress(endProg);
        return;
      }

      const tick = () => {
        const elapsed = performance.now() - startTime;
        const t = Math.min(1, elapsed / TRANSITION_MS);
        const p = startProg + (endProg - startProg) * easeOutQuart(t);
        emitProgress(p);
        if (t < 1) {
          snapRafRef.current = requestAnimationFrame(tick);
        } else {
          emitProgress(endProg);
          snapRafRef.current = 0;
        }
      };
      snapRafRef.current = requestAnimationFrame(tick);
    },
    [paneCount, emitProgress, cancelSnapRaf],
  );

  // ── Force-cancel any active gesture when locked changes ──
  useEffect(() => {
    if (locked && gestureActiveRef.current) {
      gestureActiveRef.current = false;
      const el = containerRef.current;
      if (el) {
        el.classList.remove('dragging');
        el.style.cursor = '';
      }
      snapTo(indexRef.current);
    }
  }, [locked, snapTo]);

  // ── initial position ──
  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const w = getWidth();
    el.classList.add('dragging'); // no transition on mount
    el.style.transform = `translateX(${-initialIndex * w}px)`;
    emitProgress(initialIndex);
    requestAnimationFrame(() => el.classList.remove('dragging'));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // ── resize ──
  useEffect(() => {
    const onResize = () => {
      cancelSnapRaf();
      const w = getWidth();
      if (w > 0) {
        const el = containerRef.current;
        if (el) {
          el.classList.add('dragging');
          el.style.transform = `translateX(${-indexRef.current * w}px)`;
          emitProgress(indexRef.current);
          requestAnimationFrame(() => el.classList.remove('dragging'));
        }
      }
    };
    window.addEventListener('resize', onResize);
    return () => window.removeEventListener('resize', onResize);
  }, [emitProgress, cancelSnapRaf]);

  // ── read current visual offset (for mid-transition interrupts) ──
  const readCurrentOffset = useCallback((): number => {
    const el = containerRef.current;
    if (!el) return -indexRef.current * getWidth();
    const style = getComputedStyle(el).transform;
    if (!style || style === 'none') return -indexRef.current * getWidth();
    const matrix = new DOMMatrixReadOnly(style);
    return matrix.m41;
  }, []);

  // ── touch handling (mobile) ──
  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;

    const THRESHOLD = 8;
    const VELOCITY_THRESHOLD = 0.3;
    const SNAP_RATIO = 0.25;

    let active = false;
    let direction: 'h' | 'v' | null = null;
    let startX = 0;
    let startY = 0;
    let baseOffset = 0;
    let prevX = 0;
    let prevTime = 0;
    let lastX = 0;
    let lastTime = 0;

    const onTouchStart = (e: TouchEvent) => {
      if (locked || paneCount <= 1) return;
      const t = e.touches[0];
      cancelSnapRaf();
      baseOffset = readCurrentOffset();

      el.classList.add('dragging');
      el.style.transform = `translateX(${baseOffset}px)`;

      active = true;
      gestureActiveRef.current = true;
      direction = null;
      startX = t.clientX;
      startY = t.clientY;
      const now = performance.now();
      prevX = lastX = t.clientX;
      prevTime = lastTime = now;
    };

    const onTouchMove = (e: TouchEvent) => {
      if (!active || !gestureActiveRef.current) { active = false; return; }
      const t = e.touches[0];
      const dx = t.clientX - startX;
      const dy = t.clientY - startY;

      if (!direction) {
        if (Math.abs(dx) < THRESHOLD && Math.abs(dy) < THRESHOLD) return;
        // Vertical, or horizontal but no neighbor in that direction → bail
        if (Math.abs(dy) > Math.abs(dx) || !hasNeighbor(dx)) {
          direction = 'v';
          active = false;
          gestureActiveRef.current = false;
          el.classList.remove('dragging');
          snapTo(indexRef.current);
          return;
        }
        direction = 'h';
      }

      prevX = lastX;
      prevTime = lastTime;
      lastX = t.clientX;
      lastTime = performance.now();

      const offset = clampOffset(baseOffset + dx);
      el.style.transform = `translateX(${offset}px)`;
      const w = getWidth();
      if (w > 0) emitProgress(Math.max(0, Math.min(paneCount - 1, -offset / w)));

      e.preventDefault();
    };

    const onTouchEnd = () => {
      if (!active || !gestureActiveRef.current || direction !== 'h') {
        active = false;
        gestureActiveRef.current = false;
        el.classList.remove('dragging');
        return;
      }
      active = false;
      gestureActiveRef.current = false;

      const w = getWidth();
      if (w <= 0) return;

      const currentOffset = clampOffset(baseOffset + (lastX - startX));
      const currentProg = -currentOffset / w;
      const base = indexRef.current;

      const dt = lastTime - prevTime;
      const velocity = dt > 0 && dt < 150 ? (lastX - prevX) / dt : 0;

      const target = computeTarget(currentProg, base, velocity, VELOCITY_THRESHOLD, SNAP_RATIO);
      snapTo(Math.max(0, Math.min(target, paneCount - 1)));
    };

    const onTouchCancel = () => {
      if (!active) return;
      active = false;
      gestureActiveRef.current = false;
      el.classList.remove('dragging');
      snapTo(indexRef.current);
    };

    el.addEventListener('touchstart', onTouchStart, { passive: true });
    el.addEventListener('touchmove', onTouchMove, { passive: false });
    el.addEventListener('touchend', onTouchEnd, { passive: true });
    el.addEventListener('touchcancel', onTouchCancel, { passive: true });
    return () => {
      el.removeEventListener('touchstart', onTouchStart);
      el.removeEventListener('touchmove', onTouchMove);
      el.removeEventListener('touchend', onTouchEnd);
      el.removeEventListener('touchcancel', onTouchCancel);
    };
  }, [locked, paneCount, clampOffset, hasNeighbor, emitProgress, cancelSnapRaf, readCurrentOffset, snapTo]);

  // ── mouse drag (desktop) ──
  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;

    const THRESHOLD = 5;
    const VELOCITY_THRESHOLD = 0.3;
    const SNAP_RATIO = 0.25;

    let active = false;
    let direction: 'h' | 'v' | null = null;
    let startX = 0;
    let startY = 0;
    let baseOffset = 0;
    let prevX = 0;
    let prevTime = 0;
    let lastX = 0;
    let lastTime = 0;

    // Suppress text selection and native drag during horizontal swipe
    const onDragStart = (e: Event) => { if (direction === 'h') e.preventDefault(); };
    const onSelectStart = (e: Event) => { if (direction === 'h') e.preventDefault(); };

    const onMouseDown = (e: MouseEvent) => {
      if (e.button !== 0 || locked || paneCount <= 1) return;
      cancelSnapRaf();
      baseOffset = readCurrentOffset();
      el.classList.add('dragging');
      el.style.transform = `translateX(${baseOffset}px)`;

      active = true;
      gestureActiveRef.current = true;
      direction = null;
      startX = e.clientX;
      startY = e.clientY;
      const now = performance.now();
      prevX = lastX = e.clientX;
      prevTime = lastTime = now;
    };

    const onMouseMove = (e: MouseEvent) => {
      if (!active || !gestureActiveRef.current) { active = false; return; }
      const dx = e.clientX - startX;
      const dy = e.clientY - startY;

      if (!direction) {
        if (Math.abs(dx) < THRESHOLD && Math.abs(dy) < THRESHOLD) return;
        if (Math.abs(dy) >= Math.abs(dx) || !hasNeighbor(dx)) {
          active = false;
          gestureActiveRef.current = false;
          el.classList.remove('dragging');
          snapTo(indexRef.current);
          return;
        }
        direction = 'h';
        el.style.cursor = 'grabbing';
        el.style.userSelect = 'none';
      }

      prevX = lastX;
      prevTime = lastTime;
      lastX = e.clientX;
      lastTime = performance.now();

      const offset = clampOffset(baseOffset + dx);
      el.style.transform = `translateX(${offset}px)`;
      const w = getWidth();
      if (w > 0) emitProgress(Math.max(0, Math.min(paneCount - 1, -offset / w)));
      e.preventDefault();
    };

    const onMouseUp = () => {
      if (!active || !gestureActiveRef.current) {
        active = false;
        gestureActiveRef.current = false;
        el.classList.remove('dragging');
        el.style.cursor = '';
        el.style.userSelect = '';
        return;
      }
      const wasHorizontal = direction === 'h';
      active = false;
      gestureActiveRef.current = false;
      el.style.cursor = '';
      el.style.userSelect = '';

      if (!wasHorizontal) {
        el.classList.remove('dragging');
        return;
      }

      const w = getWidth();
      if (w <= 0) return;

      const currentOffset = clampOffset(baseOffset + (lastX - startX));
      const currentProg = -currentOffset / w;
      const base = indexRef.current;

      const dt = lastTime - prevTime;
      const velocity = dt > 0 && dt < 150 ? (lastX - prevX) / dt : 0;

      const target = computeTarget(currentProg, base, velocity, VELOCITY_THRESHOLD, SNAP_RATIO);
      snapTo(Math.max(0, Math.min(target, paneCount - 1)));
    };

    el.addEventListener('mousedown', onMouseDown);
    el.addEventListener('dragstart', onDragStart);
    el.addEventListener('selectstart', onSelectStart);
    window.addEventListener('mousemove', onMouseMove);
    window.addEventListener('mouseup', onMouseUp);
    return () => {
      el.removeEventListener('mousedown', onMouseDown);
      el.removeEventListener('dragstart', onDragStart);
      el.removeEventListener('selectstart', onSelectStart);
      window.removeEventListener('mousemove', onMouseMove);
      window.removeEventListener('mouseup', onMouseUp);
    };
  }, [locked, paneCount, clampOffset, hasNeighbor, emitProgress, cancelSnapRaf, readCurrentOffset, snapTo]);

  // ── programmatic navigation ──
  const goTo = useCallback(
    (index: number) => {
      if (locked) return;
      snapTo(Math.max(0, Math.min(index, paneCount - 1)));
    },
    [locked, paneCount, snapTo],
  );

  // Cleanup rAF on unmount
  useEffect(() => cancelSnapRaf, [cancelSnapRaf]);

  return { containerRef, activeIndex, goTo };
};
