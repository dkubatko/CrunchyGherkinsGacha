import { useState, useCallback, useMemo } from 'react';

// Components
import SwipeableSubTabs from '@/components/common/SwipeableSubTabs';
import CardsView from './CardsView';
import AspectsView from './AspectsView';

// Types
import type { CardData, AspectData, AspectConfigResponse } from '@/types';

interface CollectionTabProps {
  currentUserId: number;
  targetUserId: number;
  chatId: string | null;
  isOwnCollection: boolean;
  enableTrade: boolean;
  initData: string;
  ownerLabel: string | null;
  initialCards?: CardData[];
  initialAspects?: AspectData[];
  initialConfig?: AspectConfigResponse;
  // AllTab sync callbacks
  onCardUpdate?: (cardId: number, updates: Partial<CardData>) => void;
  onAspectUpdate?: (aspectId: number, updates: Partial<AspectData>) => void;
  onAspectRemove?: (aspectId: number) => void;
  onClaimPointsUpdate?: (count: number) => void;
}

const CollectionTab = ({
  currentUserId,
  targetUserId,
  chatId,
  isOwnCollection,
  enableTrade,
  initData,
  ownerLabel,
  initialCards,
  initialAspects,
  initialConfig,
  onCardUpdate,
  onAspectUpdate,
  onAspectRemove,
  onClaimPointsUpdate,
}: CollectionTabProps) => {
  // Lock swiping when a pane is in trade/modal mode
  const [swipeLocked, setSwipeLocked] = useState(false);

  const handleLockSwipe = useCallback((locked: boolean) => {
    setSwipeLocked(locked);
  }, []);

  const SUB_TABS = useMemo(() => {
    const prefix = ownerLabel ? `${ownerLabel}'s` : '';
    const tabs = [
      { key: 'cards', label: prefix ? `${prefix} Cards` : 'Cards' },
    ];
    if (chatId) {
      tabs.push({ key: 'aspects', label: prefix ? `${prefix} Aspects` : 'Aspects' });
    }
    return tabs;
  }, [ownerLabel, chatId]);

  const hasAspects = Boolean(chatId);

  // Mark panes as visited when the scroll-snap triggers a tab change
  // We do this via a simple wrapper around the SwipeableSubTabs children
  // The isActive prop gates expensive hook fetches

  return (
    <SwipeableSubTabs
      tabs={SUB_TABS}
      locked={swipeLocked}
    >
      <CardsView
        currentUserId={currentUserId}
        targetUserId={targetUserId}
        chatId={chatId}
        isOwnCollection={isOwnCollection}
        enableTrade={enableTrade}
        initData={initData}
        ownerLabel={ownerLabel}
        initialCards={initialCards}
        initialConfig={initialConfig}
        onCardUpdate={onCardUpdate}
        onClaimPointsUpdate={onClaimPointsUpdate}
        onLockSwipe={handleLockSwipe}
      />
      {hasAspects && (
        <AspectsView
          currentUserId={currentUserId}
          chatId={chatId}
          initData={initData}
          targetUserId={targetUserId}
          ownerLabel={ownerLabel}
          initialAspects={initialAspects}
          initialConfig={initialConfig}
          onAspectUpdate={onAspectUpdate}
          onAspectRemove={onAspectRemove}
          onClaimPointsUpdate={onClaimPointsUpdate}
          onLockSwipe={handleLockSwipe}
        />
      )}
    </SwipeableSubTabs>
  );
};

export default CollectionTab;
