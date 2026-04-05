// Components
import SwipeableSubTabs from '@/components/common/SwipeableSubTabs';
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

const SUB_TABS = [
  { key: 'cards', label: 'All Cards' },
  { key: 'aspects', label: 'All Aspects' },
];

const AllTab = ({ initData, currentUserId, initialAllCards, initialAllAspects }: AllTabProps) => {
  const allCards = initialAllCards ?? [];
  const allAspects = initialAllAspects ?? [];

  return (
    <SwipeableSubTabs tabs={SUB_TABS}>
      <CardsView
        currentUserId={currentUserId}
        chatId={null}
        initData={initData}
        ownerLabel={null}
        isReadOnly
        allCards={allCards}
      />
      <AspectsView
        currentUserId={currentUserId}
        chatId={null}
        initData={initData}
        ownerLabel={null}
        isReadOnly
        allAspects={allAspects}
      />
    </SwipeableSubTabs>
  );
};

export default AllTab;
