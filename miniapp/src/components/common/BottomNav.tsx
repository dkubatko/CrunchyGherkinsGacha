import React from 'react';
import type { HubTab } from '@/types';
import './BottomNav.css';

interface BottomNavProps {
  activeTab: HubTab;
  onTabChange: (tab: HubTab) => void;
  disabledTabs: Set<HubTab>;
}

const ProfileIcon = () => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2" />
    <circle cx="12" cy="7" r="4" />
  </svg>
);

const CollectionIcon = () => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <rect x="3" y="3" width="7" height="9" rx="1" />
    <rect x="14" y="3" width="7" height="5" rx="1" />
    <rect x="14" y="12" width="7" height="9" rx="1" />
    <rect x="3" y="16" width="7" height="5" rx="1" />
  </svg>
);

const CasinoIcon = () => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <rect x="3" y="3" width="18" height="18" rx="3" />
    <line x1="3" y1="9" x2="21" y2="9" />
    <line x1="3" y1="15" x2="21" y2="15" />
    <line x1="9" y1="3" x2="9" y2="21" />
    <line x1="15" y1="3" x2="15" y2="21" />
    <circle cx="6" cy="12" r="1.5" fill="currentColor" stroke="none" />
    <circle cx="12" cy="12" r="1.5" fill="currentColor" stroke="none" />
    <circle cx="18" cy="12" r="1.5" fill="currentColor" stroke="none" />
  </svg>
);

const AllCardsIcon = () => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <rect x="4" y="1" width="16" height="18" rx="2" />
    <rect x="2" y="4" width="16" height="18" rx="2" fill="var(--tg-theme-bg-color, #242424)" />
    <rect x="2" y="4" width="16" height="18" rx="2" />
  </svg>
);

const TAB_CONFIG: { key: HubTab; label: string; Icon: React.FC }[] = [
  { key: 'profile', label: 'Profile', Icon: ProfileIcon },
  { key: 'collection', label: 'Collection', Icon: CollectionIcon },
  { key: 'casino', label: 'Casino', Icon: CasinoIcon },
  { key: 'allCards', label: 'All Cards', Icon: AllCardsIcon },
];

const BottomNav: React.FC<BottomNavProps> = ({ activeTab, onTabChange, disabledTabs }) => {
  return (
    <nav className="bottom-nav">
      {TAB_CONFIG.map(({ key, label, Icon }) => {
        const isDisabled = disabledTabs.has(key);
        const isActive = activeTab === key;

        return (
          <button
            key={key}
            className={`bottom-nav-item ${isActive ? 'active' : ''} ${isDisabled ? 'disabled' : ''}`}
            onClick={() => !isDisabled && onTabChange(key)}
            disabled={isDisabled}
            aria-label={label}
            aria-current={isActive ? 'page' : undefined}
          >
            <span className="bottom-nav-icon">
              <Icon />
            </span>
            <span className="bottom-nav-label">{label}</span>
          </button>
        );
      })}
    </nav>
  );
};

export default BottomNav;
