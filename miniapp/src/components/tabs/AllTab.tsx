// Components
import SwipeableSubTabs from '@/components/common/SwipeableSubTabs';
import CardsView from './CardsView';
import AspectsView from './AspectsView';

// Hooks
import { useAllCards } from '@/hooks/useAllCards';
import { useAllAspects } from '@/hooks/useAllAspects';

// Types
import type { CardData, AspectData, PendingOpenItem } from '@/types';

interface AllTabProps {
  initData: string;
  currentUserId: number;
  chatId: string;
  initialAllCards?: CardData[];
  initialAllAspects?: AspectData[];
  pendingOpenItem?: PendingOpenItem | null;
}

const SUB_TABS = [
  { key: 'cards', label: 'All Cards' },
  { key: 'aspects', label: 'All Aspects' },
];

const AllTab = ({ initData, currentUserId, chatId, pendingOpenItem }: AllTabProps) => {
  const { allCards, refetch: refetchAllCards } = useAllCards(initData, chatId);
  const { allAspects, refetch: refetchAllAspects } = useAllAspects(initData, chatId);

  const initialIndex = pendingOpenItem?.type === 'aspect' ? 1 : 0;

  return (
    <SwipeableSubTabs tabs={SUB_TABS} initialIndex={initialIndex}>
      <CardsView
        currentUserId={currentUserId}
        chatId={chatId}
        initData={initData}
        ownerLabel={null}
        isReadOnly
        allCards={allCards}
        onRefresh={refetchAllCards}
        pendingOpenCardId={pendingOpenItem?.type === 'card' ? pendingOpenItem.id : null}
      />
      <AspectsView
        currentUserId={currentUserId}
        chatId={chatId}
        initData={initData}
        ownerLabel={null}
        isReadOnly
        allAspects={allAspects}
        onRefresh={refetchAllAspects}
        pendingOpenAspectId={pendingOpenItem?.type === 'aspect' ? pendingOpenItem.id : null}
      />
    </SwipeableSubTabs>
  );
};

export default AllTab;
