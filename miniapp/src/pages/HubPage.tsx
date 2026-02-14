import { useState, useCallback, useEffect, useRef, useMemo } from 'react';
import '@/App.css';
import './HubPage.css';

// Components
import BottomNav from '@/components/common/BottomNav';
import ProfileTab from '@/components/tabs/ProfileTab';
import CollectionTab from '@/components/tabs/CollectionTab';
import CasinoTab from '@/components/tabs/CasinoTab';
import AllCardsTab from '@/components/tabs/AllCardsTab';

// Utils
import { TelegramUtils } from '@/utils/telegram';

// Types
import type { HubTab } from '@/types';

interface HubPageProps {
  currentUserId: number;
  targetUserId: number;
  chatId: string | null;
  isOwnCollection: boolean;
  enableTrade: boolean;
  initData: string;
  initialTab: HubTab;
}

export const HubPage = ({
  currentUserId,
  targetUserId,
  chatId,
  isOwnCollection,
  enableTrade,
  initData,
  initialTab,
}: HubPageProps) => {
  const [activeTab, setActiveTab] = useState<HubTab>(initialTab);
  // Track which tabs have been visited so we can keep them mounted
  const [mountedTabs, setMountedTabs] = useState<Set<HubTab>>(new Set([initialTab]));
  const expandedRef = useRef(false);

  // Tabs that require chat_id
  const disabledTabs = useMemo(() => {
    const disabled = new Set<HubTab>();
    if (!chatId) {
      disabled.add('profile');
      disabled.add('casino');
      disabled.add('allCards');
    }
    return disabled;
  }, [chatId]);

  // Expand app on mount
  useEffect(() => {
    if (expandedRef.current) return;
    expandedRef.current = true;
    TelegramUtils.expandApp();
  }, []);

  const handleTabChange = useCallback((tab: HubTab) => {
    setActiveTab(tab);
    setMountedTabs(prev => {
      if (prev.has(tab)) return prev;
      const next = new Set(prev);
      next.add(tab);
      return next;
    });
  }, []);

  return (
    <div className="hub-container">
      <div className="hub-content">
        {/* Profile Tab */}
        {mountedTabs.has('profile') && (
          <div className={`hub-tab-panel ${activeTab === 'profile' ? 'active' : ''}`}>
            <ProfileTab
              currentUserId={currentUserId}
              targetUserId={targetUserId}
              isOwnCollection={isOwnCollection}
              chatId={chatId}
              initData={initData}
            />
          </div>
        )}

        {/* Collection Tab */}
        {mountedTabs.has('collection') && (
          <div className={`hub-tab-panel ${activeTab === 'collection' ? 'active' : ''}`}>
            <CollectionTab
              currentUserId={currentUserId}
              targetUserId={targetUserId}
              chatId={chatId}
              isOwnCollection={isOwnCollection}
              enableTrade={enableTrade}
              initData={initData}
            />
          </div>
        )}

        {/* Casino Tab */}
        {mountedTabs.has('casino') && chatId && (
          <div className={`hub-tab-panel ${activeTab === 'casino' ? 'active' : ''}`}>
            <CasinoTab
              currentUserId={currentUserId}
              chatId={chatId}
              initData={initData}
            />
          </div>
        )}

        {/* All Cards Tab */}
        {mountedTabs.has('allCards') && chatId && (
          <div className={`hub-tab-panel ${activeTab === 'allCards' ? 'active' : ''}`}>
            <AllCardsTab
              chatId={chatId}
              initData={initData}
            />
          </div>
        )}
      </div>

      <BottomNav
        activeTab={activeTab}
        onTabChange={handleTabChange}
        disabledTabs={disabledTabs}
      />
    </div>
  );
};
