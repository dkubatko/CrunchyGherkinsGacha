import React, { useEffect, useRef, useState } from 'react';
import './ClaimPointsBadge.css';

export interface ClaimPointsBadgeProps {
  count: number;
}

const ClaimPointsBadge: React.FC<ClaimPointsBadgeProps> = ({ count }) => {
  const [display, setDisplay] = useState(count);
  const [glowing, setGlowing] = useState(false);
  const prevRef = useRef(count);
  const rafRef = useRef<number | null>(null);

  useEffect(() => {
    const from = prevRef.current;
    const to = count;
    prevRef.current = count;

    if (from === to) {
      setDisplay(to);
      return;
    }

    const increasing = to > from;
    if (increasing) setGlowing(true);
    const diff = to - from;

    // Single-unit changes are instant
    if (Math.abs(diff) === 1) {
      setDisplay(to);
      setGlowing(false);
      return;
    }

    const duration = Math.min(2000, Math.max(1000, Math.abs(diff) * 50));
    const start = performance.now();

    const tick = (now: number) => {
      const elapsed = now - start;
      const t = Math.min(elapsed / duration, 1);
      const eased = Math.sqrt(t);
      setDisplay(Math.round(from + diff * eased));
      if (t < 1) {
        rafRef.current = requestAnimationFrame(tick);
      } else {
        setGlowing(false);
      }
    };

    rafRef.current = requestAnimationFrame(tick);
    return () => {
      if (rafRef.current) cancelAnimationFrame(rafRef.current);
    };
  }, [count]);

  return (
    <div className={`cpb-badge${glowing ? ' cpb-glow' : ''}`}>
      <span className="cpb-coin" aria-hidden="true">C</span>
      <span className="cpb-count">{display}</span>
    </div>
  );
};

export default ClaimPointsBadge;
