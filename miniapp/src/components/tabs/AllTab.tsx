// Components
import SwipeableSubTabs from '@/components/common/SwipeableSubTabs';
import CardsView from './CardsView';
import AspectsView from './AspectsView';

// Hooks
import { useAllCards } from '@/hooks/useAllCards';
import { useAllAspects } from '@/hooks/useAllAspects';

// Types
import type { CardData, AspectData } from '@/types';

interface AllTabProps {
  initData: string;
  currentUserId: number;
  chatId: string;
  initialAllCards?: CardData[];
  initialAllAspects?: AspectData[];
}

const SUB_TABS = [
  { key: 'cards', label: 'All Cards' },
  { key: 'aspects', label: 'All Aspects' },
];

const AllTab = ({ initData, currentUserId, chatId }: AllTabProps) => {
  const { allCards, refetch: refetchAllCards } = useAllCards(initData, chatId);
  const { allAspects, refetch: refetchAllAspects } = useAllAspects(initData, chatId);

  return (
    <SwipeableSubTabs tabs={SUB_TABS}>
      <CardsView
        currentUserId={currentUserId}
        chatId={chatId}
        initData={initData}
        ownerLabel={null}
        isReadOnly
        allCards={allCards}
        onRefresh={refetchAllCards}
      />
      <AspectsView
        currentUserId={currentUserId}
        chatId={chatId}
        initData={initData}
        ownerLabel={null}
        isReadOnly
        allAspects={allAspects}
        onRefresh={refetchAllAspects}
      />
    </SwipeableSubTabs>
  );
};

export default AllTab;
