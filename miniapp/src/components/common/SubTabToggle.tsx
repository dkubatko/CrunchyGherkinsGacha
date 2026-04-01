import React from 'react';
import './SubTabToggle.css';

interface SubTabToggleProps {
  tabs: { key: string; label: string }[];
  activeTab: string;
  onChange: (key: string) => void;
}

const SubTabToggle: React.FC<SubTabToggleProps> = ({ tabs, activeTab, onChange }) => {
  return (
    <div className="subtab-toggle">
      {tabs.map(({ key, label }) => (
        <button
          key={key}
          className={`subtab-toggle-item ${activeTab === key ? 'active' : ''}`}
          onClick={() => onChange(key)}
          aria-pressed={activeTab === key}
        >
          {label}
        </button>
      ))}
    </div>
  );
};

export default SubTabToggle;
