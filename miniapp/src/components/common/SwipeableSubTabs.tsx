import React, { useCallback, useRef, useEffect } from 'react';
import SubTabToggle from './SubTabToggle';
import { useScrollSnap } from '@/hooks/useScrollSnap';
import './SwipeableSubTabs.css';

interface SwipeableSubTabsProps {
  tabs: { key: string; label: string }[];
  locked?: boolean;
  children: React.ReactNode[];
}

/**
 * Horizontal swipeable pane container with a synced SubTabToggle indicator.
 * Uses CSS transforms for GPU-composited pane positioning.
 * Touch-action: pan-y lets the browser handle vertical scroll natively;
 * JS handles horizontal gestures with direction locking and clamped translation.
 */
const SwipeableSubTabs: React.FC<SwipeableSubTabsProps> = ({ tabs, locked = false, children }) => {
  const paneCount = React.Children.count(children);
  const indicatorRef = useRef<HTMLDivElement>(null);
  const buttonRefs = useRef<(HTMLButtonElement | null)[]>([]);

  // Direct DOM updates — no React re-renders during scroll
  const handleProgress = useCallback((p: number) => {
    if (indicatorRef.current) {
      indicatorRef.current.style.transform = `translateX(${p * 100}%)`;
    }
    buttonRefs.current.forEach((btn, i) => {
      if (btn) {
        const distance = Math.abs(p - i);
        btn.style.opacity = String(Math.max(0.5, 1 - distance * 0.5));
      }
    });
  }, []);

  const { containerRef, activeIndex, goTo } = useScrollSnap({
    paneCount,
    initialIndex: 0,
    locked,
    onProgress: handleProgress,
  });

  // Set initial indicator position on mount
  useEffect(() => { handleProgress(0); }, [handleProgress]);

  const handleTabChange = useCallback((key: string) => {
    const idx = tabs.findIndex(t => t.key === key);
    if (idx >= 0) goTo(idx);
  }, [tabs, goTo]);

  // Single-pane fallback: no toggle, no scroll
  if (paneCount <= 1) {
    return (
      <div className="swipeable-subtabs">
        <div className="swipeable-subtabs-pane">
          {React.Children.toArray(children)[0]}
        </div>
      </div>
    );
  }

  const activeTab = tabs[activeIndex]?.key ?? tabs[0]?.key ?? '';

  return (
    <div className="swipeable-subtabs">
      <div className="swipeable-subtabs-header">
        <SubTabToggle
          tabs={tabs}
          activeTab={activeTab}
          onChange={handleTabChange}
          indicatorRef={indicatorRef}
          buttonRefs={buttonRefs}
        />
      </div>
      <div ref={containerRef} className="swipeable-subtabs-track">
        {React.Children.map(children, (child, i) => (
          <div key={tabs[i]?.key ?? i} className="swipeable-subtabs-pane">
            {child}
          </div>
        ))}
      </div>
    </div>
  );
};

export default SwipeableSubTabs;
