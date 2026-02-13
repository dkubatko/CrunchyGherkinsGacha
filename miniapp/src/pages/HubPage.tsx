import { useState, useCallback, useEffect, useRef, Suspense, lazy, useMemo } from 'react';
import '@/App.css';
import './HubPage.css';

// Components
import BottomNav from '@/components/common/BottomNav';
import Loading from '@/components/common/Loading';

// Utils
import { TelegramUtils } from '@/utils/telegram';

// Types
import type { HubTab } from '@/types';

// Lazy-loaded tab components
const ProfileTab = lazy(() => import('@/components/tabs/ProfileTab'));
const CollectionTab = lazy(() => import('@/components/tabs/CollectionTab'));
const CasinoTab = lazy(() => import('@/components/tabs/CasinoTab'));
const AllCardsTab = lazy(() => import('@/components/tabs/AllCardsTab'));

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
            <Suspense fallback={<Loading message="Loading profile..." />}>
              <ProfileTab
                currentUserId={currentUserId}
                targetUserId={targetUserId}
                isOwnCollection={isOwnCollection}
                chatId={chatId}
                initData={initData}
              />
            </Suspense>
          </div>
        )}

        {/* Collection Tab */}
        {mountedTabs.has('collection') && (
          <div className={`hub-tab-panel ${activeTab === 'collection' ? 'active' : ''}`}>
            <Suspense fallback={<Loading message="Loading collection..." />}>
              <CollectionTab
                currentUserId={currentUserId}
                targetUserId={targetUserId}
                chatId={chatId}
                isOwnCollection={isOwnCollection}
                enableTrade={enableTrade}
                initData={initData}
              />
            </Suspense>
          </div>
        )}

        {/* Casino Tab */}
        {mountedTabs.has('casino') && chatId && (
          <div className={`hub-tab-panel ${activeTab === 'casino' ? 'active' : ''}`}>
            <Suspense fallback={<Loading message="Loading casino..." />}>
              <CasinoTab
                currentUserId={currentUserId}
                chatId={chatId}
                initData={initData}
              />
            </Suspense>
          </div>
        )}

        {/* All Cards Tab */}
        {mountedTabs.has('allCards') && chatId && (
          <div className={`hub-tab-panel ${activeTab === 'allCards' ? 'active' : ''}`}>
            <Suspense fallback={<Loading message="Loading all cards..." />}>
              <AllCardsTab
                chatId={chatId}
                initData={initData}
              />
            </Suspense>
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
