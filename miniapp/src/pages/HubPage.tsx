import { useState, useCallback, useEffect, useRef, useMemo } from 'react';
import '@/App.css';
import './HubPage.css';

// Components
import BottomNav from '@/components/common/BottomNav';
import ProfileTab from '@/components/tabs/ProfileTab';
import CollectionTab from '@/components/tabs/CollectionTab';
import CasinoTab from '@/components/tabs/CasinoTab';
import AllCardsTab from '@/components/tabs/AllCardsTab';

// Services
import { ApiService } from '@/services/api';

// Utils
import { TelegramUtils } from '@/utils/telegram';

// Types
import type { HubTab, UserProfile } from '@/types';

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

  // Shared user profile state
  const [profile, setProfile] = useState<UserProfile | null>(null);
  const [profileLoading, setProfileLoading] = useState(true);
  const [profileError, setProfileError] = useState<string | undefined>();
  const profileFetchedRef = useRef(false);

  useEffect(() => {
    if (profileFetchedRef.current || !chatId) {
      setProfileLoading(false);
      if (!chatId) setProfileError('Profile is unavailable outside a chat context.');
      return;
    }
    profileFetchedRef.current = true;

    const userId = isOwnCollection ? currentUserId : targetUserId;
    ApiService.fetchUserProfile(userId, chatId, initData)
      .then((result) => setProfile(result))
      .catch((err) => setProfileError(err instanceof Error ? err.message : 'Failed to load profile'))
      .finally(() => setProfileLoading(false));
  }, [currentUserId, targetUserId, isOwnCollection, chatId, initData]);

  // Claim points derived from profile, updatable in real-time by casino games
  const [claimPointsOverride, setClaimPointsOverride] = useState<number | null>(null);
  const claimPoints = claimPointsOverride ?? profile?.claim_balance ?? null;

  const updateClaimPoints = useCallback((count: number) => {
    setClaimPointsOverride(count);
  }, []);

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
              profile={profile}
              loading={profileLoading}
              error={profileError}
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
              claimPoints={claimPoints}
              updateClaimPoints={updateClaimPoints}
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
