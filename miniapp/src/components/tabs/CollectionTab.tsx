import { useState, useCallback, useMemo } from 'react';

// Components
import { SubTabToggle } from '@/components/common';
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

type CollectionSubTab = 'cards' | 'aspects';

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
  // Sub-tab state
  const [activeSubTab, setActiveSubTab] = useState<CollectionSubTab>('cards');
  const [mountedSubTabs, setMountedSubTabs] = useState<Set<CollectionSubTab>>(new Set(['cards']));

  const SUB_TABS = useMemo(() => {
    const prefix = ownerLabel ? `${ownerLabel}'s` : '';
    return [
      { key: 'cards', label: prefix ? `${prefix} Cards` : 'Cards' },
      { key: 'aspects', label: prefix ? `${prefix} Aspects` : 'Aspects' },
    ];
  }, [ownerLabel]);

  const handleSubTabChange = useCallback((key: string) => {
    const tab = key as CollectionSubTab;
    setActiveSubTab(tab);
    setMountedSubTabs(prev => {
      if (prev.has(tab)) return prev;
      const next = new Set(prev);
      next.add(tab);
      return next;
    });
  }, []);

  return (
    <>
      {/* Cards sub-tab */}
      {mountedSubTabs.has('cards') && (
        <div style={{ display: activeSubTab === 'cards' ? 'contents' : 'none' }}>
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
            header={<SubTabToggle tabs={SUB_TABS} activeTab={activeSubTab} onChange={handleSubTabChange} />}
          />
        </div>
      )}

      {/* Aspects sub-tab */}
      {mountedSubTabs.has('aspects') && chatId && (
        <div style={{ display: activeSubTab === 'aspects' ? 'contents' : 'none' }}>
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
            header={<SubTabToggle tabs={SUB_TABS} activeTab={activeSubTab} onChange={handleSubTabChange} />}
          />
        </div>
      )}
    </>
  );
};

export default CollectionTab;
