import { useState, useCallback, useEffect, useRef, useMemo } from 'react';
import '@/App.css';
import './HubPage.css';

// Components
import BottomNav from '@/components/common/BottomNav';
import SplashScreen from '@/components/common/SplashScreen';
import ProfileTab from '@/components/tabs/ProfileTab';
import CollectionTab from '@/components/tabs/CollectionTab';
import CasinoTab from '@/components/tabs/CasinoTab';
import AllTab from '@/components/tabs/AllTab';

// Utils
import { TelegramUtils } from '@/utils/telegram';

// Hooks
import { useHubData } from '@/hooks';

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
  const [splashDismissed, setSplashDismissed] = useState(false);
  const [currentSpinBalance, setCurrentSpinBalance] = useState<number | null>(null);

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

  // ── Centralized data prefetching ──
  const {
    profile,
    profileError,
    collection,
    aspects,
    allCards,
    allChatAspects,
    casino,
    config,
    ready,
    progress,
    refreshProfile,
    updateCardInAll,
    updateAspectInAll,
    removeAspectFromAll,
    claimPoints,
    updateClaimPoints,
  } = useHubData({ currentUserId, targetUserId, chatId, initData });

  const ownerLabel = useMemo(() => {
    if (profile?.display_name) return profile.display_name;
    if (profile?.username) return `@${profile.username}`;
    return null;
  }, [profile]);

  const handleTabChange = useCallback((tab: HubTab) => {
    setActiveTab(tab);
    setMountedTabs(prev => {
      if (prev.has(tab)) return prev;
      const next = new Set(prev);
      next.add(tab);
      return next;
    });
  }, []);

  const handleSplashDone = useCallback(() => {
    setSplashDismissed(true);
  }, []);

  return (
    <div className="hub-container">
      {/* Splash screen overlay — shown until data is ready + animation completes */}
      {!splashDismissed && (
        <SplashScreen progress={progress} ready={ready} onTransitionEnd={handleSplashDone} />
      )}

      <div className="hub-content">
        {/* Profile Tab */}
        {ready && mountedTabs.has('profile') && (
          <div className={`hub-tab-panel ${activeTab === 'profile' ? 'active' : ''}`}>
            <ProfileTab
              profile={profile}
              loading={!ready}
              error={profileError ?? undefined}
              isActive={activeTab === 'profile'}
              onRefresh={refreshProfile}
            />
          </div>
        )}

        {/* Collection Tab */}
        {ready && mountedTabs.has('collection') && (
          <div className={`hub-tab-panel ${activeTab === 'collection' ? 'active' : ''}`}>
            <CollectionTab
              currentUserId={currentUserId}
              targetUserId={collection?.userId ?? targetUserId}
              chatId={chatId}
              isOwnCollection={collection?.isOwnCollection ?? isOwnCollection}
              enableTrade={collection?.enableTrade ?? enableTrade}
              initData={initData}
              ownerLabel={ownerLabel}
              initialCards={collection?.cards}
              initialAspects={aspects}
              initialConfig={config ?? undefined}
              onCardUpdate={updateCardInAll}
              onAspectUpdate={updateAspectInAll}
              onAspectRemove={removeAspectFromAll}
              onClaimPointsUpdate={updateClaimPoints}
              onSpinsUpdate={setCurrentSpinBalance}
            />
          </div>
        )}

        {/* Casino Tab */}
        {ready && mountedTabs.has('casino') && chatId && (
          <div className={`hub-tab-panel ${activeTab === 'casino' ? 'active' : ''}`}>
            <CasinoTab
              currentUserId={currentUserId}
              chatId={chatId}
              initData={initData}
              initialCasinoData={casino ?? undefined}
              claimPoints={claimPoints}
              onClaimPointsUpdate={updateClaimPoints}
              currentSpinBalance={currentSpinBalance}
            />
          </div>
        )}

        {/* All Tab */}
        {ready && mountedTabs.has('allCards') && chatId && (
          <div className={`hub-tab-panel ${activeTab === 'allCards' ? 'active' : ''}`}>
            <AllTab
              initData={initData}
              currentUserId={currentUserId}
              chatId={chatId}
              initialAllCards={allCards}
              initialAllAspects={allChatAspects}
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
