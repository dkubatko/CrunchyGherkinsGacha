import React, { useEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';

export interface AdminPopoverProps {
  anchor: HTMLElement | null;
  onClose: () => void;
  className?: string;
  children: React.ReactNode;
  matchAnchorWidth?: boolean;
}

const AdminPopover: React.FC<AdminPopoverProps> = ({
  anchor,
  onClose,
  className = '',
  children,
  matchAnchorWidth = false,
}) => {
  const ref = useRef<HTMLDivElement>(null);
  const didScrollToSelectedRef = useRef(false);
  const [pos, setPos] = useState<{
    top: number;
    left: number;
    maxHeight: number;
    width?: number;
  } | null>(null);

  useEffect(() => {
    if (!anchor) return;
    const update = () => {
      const rect = anchor.getBoundingClientRect();
      const spaceBelow = window.innerHeight - rect.bottom - 8;
      const spaceAbove = rect.top - 8;
      const PREFERRED_MAX = 260;
      let top: number;
      let maxHeight: number;
      if (spaceBelow >= Math.min(PREFERRED_MAX, 120) || spaceBelow >= spaceAbove) {
        top = rect.bottom + 4;
        maxHeight = Math.max(120, Math.min(PREFERRED_MAX, spaceBelow));
      } else {
        maxHeight = Math.max(120, Math.min(PREFERRED_MAX, spaceAbove));
        top = rect.top - 4 - maxHeight;
      }
      setPos({
        top,
        left: rect.left,
        maxHeight,
        width: matchAnchorWidth ? rect.width : undefined,
      });
    };
    update();
    window.addEventListener('scroll', update, true);
    window.addEventListener('resize', update);
    return () => {
      window.removeEventListener('scroll', update, true);
      window.removeEventListener('resize', update);
    };
  }, [anchor, matchAnchorWidth]);

  useEffect(() => {
    const handler = (e: MouseEvent) => {
      const target = e.target as Node;
      if (ref.current && ref.current.contains(target)) return;
      if (anchor && anchor.contains(target)) return;
      onClose();
    };
    const keyHandler = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    const t = setTimeout(() => document.addEventListener('mousedown', handler), 0);
    document.addEventListener('keydown', keyHandler);
    return () => {
      clearTimeout(t);
      document.removeEventListener('mousedown', handler);
      document.removeEventListener('keydown', keyHandler);
    };
  }, [onClose, anchor]);

  if (!pos) return null;
  return createPortal(
    <div
      ref={(node) => {
        ref.current = node;
        if (node && !didScrollToSelectedRef.current) {
          const selected = node.querySelector('.admin-popover-item--selected') as HTMLElement | null;
          if (selected) {
            const itemTop = selected.offsetTop;
            const itemHeight = selected.offsetHeight;
            const listHeight = node.clientHeight;
            node.scrollTop = Math.max(0, itemTop - (listHeight - itemHeight) / 2);
          }
          didScrollToSelectedRef.current = true;
        }
      }}
      className={`admin-popover ${className}`}
      style={{
        position: 'fixed',
        top: pos.top,
        left: pos.left,
        maxHeight: pos.maxHeight,
        ...(pos.width ? { minWidth: pos.width } : {}),
      }}
    >
      {children}
    </div>,
    document.body,
  );
};

export default AdminPopover;
