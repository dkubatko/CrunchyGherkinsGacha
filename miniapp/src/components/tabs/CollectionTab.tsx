import { useState, useCallback, useMemo, useEffect, useRef } from 'react';

// Components
import SwipeableSubTabs from '@/components/common/SwipeableSubTabs';
import CardsView from './CardsView';
import AspectsView from './AspectsView';

// Utils
import { TelegramUtils } from '@/utils/telegram';

// Types
import type { CardData, AspectData, AspectConfigResponse, TradeOffer, PendingOpenItem } from '@/types';

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
  onSpinsUpdate?: (count: number) => void;
  // Deep-link request to open a specific item
  pendingOpenItem?: PendingOpenItem | null;
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
  onSpinsUpdate,
  pendingOpenItem,
}: CollectionTabProps) => {
  // Trade state — lifted here so both tabs can show trade options
  const [tradeOffer, setTradeOffer] = useState<TradeOffer | null>(null);

  const handleTradeInitiate = useCallback((offer: TradeOffer) => {
    setTradeOffer(offer);
  }, []);

  const handleTradeClose = useCallback(() => {
    setTradeOffer(null);
    TelegramUtils.hideBackButton();
  }, []);

  // Back button for trade mode
  const tradeCloseRef = useRef(handleTradeClose);
  useEffect(() => {
    tradeCloseRef.current = handleTradeClose;
  }, [handleTradeClose]);

  useEffect(() => {
    if (!tradeOffer) return;
    const cleanup = TelegramUtils.setupBackButton(() => {
      tradeCloseRef.current();
    });
    return cleanup;
  }, [tradeOffer]);

  const SUB_TABS = useMemo(() => {
    if (tradeOffer) {
      return [
        { key: 'cards', label: 'Cards' },
        { key: 'aspects', label: 'Aspects' },
      ];
    }
    const prefix = ownerLabel ? `${ownerLabel}'s` : '';
    const tabs = [
      { key: 'cards', label: prefix ? `${prefix} Cards` : 'Cards' },
    ];
    if (chatId) {
      tabs.push({ key: 'aspects', label: prefix ? `${prefix} Aspects` : 'Aspects' });
    }
    return tabs;
  }, [ownerLabel, chatId, tradeOffer]);

  const hasAspects = Boolean(chatId) || Boolean(tradeOffer);

  const pendingSubTabIndex = useMemo(() => {
    if (!pendingOpenItem) return 0;
    if (pendingOpenItem.type === 'aspect' && hasAspects) {
      // Aspects pane index depends on whether it's actually mounted
      const aspectsTabIdx = SUB_TABS.findIndex(t => t.key === 'aspects');
      return aspectsTabIdx >= 0 ? aspectsTabIdx : 0;
    }
    return 0;
  }, [pendingOpenItem, hasAspects, SUB_TABS]);

  return (
    <SwipeableSubTabs
      tabs={SUB_TABS}
      initialIndex={pendingSubTabIndex}
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
        tradeOffer={tradeOffer}
        onTradeInitiate={handleTradeInitiate}
        pendingOpenCardId={pendingOpenItem?.type === 'card' ? pendingOpenItem.id : null}
      />
      {hasAspects && (
        <AspectsView
          currentUserId={currentUserId}
          chatId={chatId}
          initData={initData}
          ownerLabel={ownerLabel}
          targetUserId={targetUserId}
          initialAspects={initialAspects}
          initialConfig={initialConfig}
          onAspectUpdate={onAspectUpdate}
          onAspectRemove={onAspectRemove}
          onClaimPointsUpdate={onClaimPointsUpdate}
          onSpinsUpdate={onSpinsUpdate}
          tradeOffer={tradeOffer}
          onTradeInitiate={handleTradeInitiate}
          pendingOpenAspectId={pendingOpenItem?.type === 'aspect' ? pendingOpenItem.id : null}
        />
      )}
    </SwipeableSubTabs>
  );
};

export default CollectionTab;
