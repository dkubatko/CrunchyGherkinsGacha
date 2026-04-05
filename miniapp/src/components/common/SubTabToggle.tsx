import React from 'react';
import './SubTabToggle.css';

interface SubTabToggleProps {
  tabs: { key: string; label: string }[];
  activeTab: string;
  onChange: (key: string) => void;
  /** Ref for the sliding indicator element (direct DOM animation by parent) */
  indicatorRef?: React.RefObject<HTMLDivElement | null>;
  /** Refs array for tab buttons (direct DOM opacity animation by parent) */
  buttonRefs?: React.MutableRefObject<(HTMLButtonElement | null)[]>;
}

const SubTabToggle: React.FC<SubTabToggleProps> = ({
  tabs, activeTab, onChange, indicatorRef, buttonRefs,
}) => {
  const tabCount = tabs.length;
  const indicatorWidthPercent = 100 / tabCount;

  return (
    <div className="subtab-toggle">
      {tabs.map(({ key, label }, i) => (
        <button
          key={key}
          ref={el => { if (buttonRefs) buttonRefs.current[i] = el; }}
          className={`subtab-toggle-item ${activeTab === key ? 'active' : ''}`}
          onClick={() => onChange(key)}
          aria-pressed={activeTab === key}
        >
          {label}
        </button>
      ))}
      <div
        ref={indicatorRef}
        className="subtab-toggle-indicator"
        style={{ width: `${indicatorWidthPercent}%` }}
      />
    </div>
  );
};

export default SubTabToggle;
