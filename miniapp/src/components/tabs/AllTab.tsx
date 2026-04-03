import { useState, useCallback } from 'react';

// Components
import { SubTabToggle } from '@/components/common';
import CardsView from './CardsView';
import AspectsView from './AspectsView';

// Types
import type { CardData, AspectData } from '@/types';

interface AllTabProps {
  initData: string;
  currentUserId: number;
  initialAllCards?: CardData[];
  initialAllAspects?: AspectData[];
}

type AllSubTab = 'cards' | 'aspects';

const SUB_TABS = [
  { key: 'cards', label: 'All Cards' },
  { key: 'aspects', label: 'All Aspects' },
];

const AllTab = ({ initData, currentUserId, initialAllCards, initialAllAspects }: AllTabProps) => {
  // Sub-tab state
  const [activeSubTab, setActiveSubTab] = useState<AllSubTab>('cards');
  const [mountedSubTabs, setMountedSubTabs] = useState<Set<AllSubTab>>(new Set(['cards']));

  // Use prefetched data directly from props (reactive to parent updates)
  const allCards = initialAllCards ?? [];
  const allAspects = initialAllAspects ?? [];

  const handleSubTabChange = useCallback((key: string) => {
    const tab = key as AllSubTab;
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
      {/* Cards sub-tab (read-only) */}
      {mountedSubTabs.has('cards') && (
        <div style={{ display: activeSubTab === 'cards' ? 'contents' : 'none' }}>
          <CardsView
            currentUserId={currentUserId}
            chatId={null}
            initData={initData}
            ownerLabel={null}
            isReadOnly
            allCards={allCards}
            header={<SubTabToggle tabs={SUB_TABS} activeTab={activeSubTab} onChange={handleSubTabChange} />}
          />
        </div>
      )}

      {/* Aspects sub-tab (read-only) */}
      {mountedSubTabs.has('aspects') && (
        <div style={{ display: activeSubTab === 'aspects' ? 'contents' : 'none' }}>
          <AspectsView
            currentUserId={currentUserId}
            chatId={null}
            initData={initData}
            ownerLabel={null}
            isReadOnly
            allAspects={allAspects}
            header={<SubTabToggle tabs={SUB_TABS} activeTab={activeSubTab} onChange={handleSubTabChange} />}
          />
        </div>
      )}
    </>
  );
};

export default AllTab;
