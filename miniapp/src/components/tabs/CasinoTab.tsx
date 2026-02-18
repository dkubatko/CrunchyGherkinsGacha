import { useState, useEffect, useRef, useCallback } from 'react';
import { Casino } from '@/components/casino';
import Loading from '@/components/common/Loading';
import { useSlots } from '@/hooks';
import { ApiService } from '@/services/api';

interface CasinoTabProps {
  currentUserId: number;
  chatId: string;
  initData: string;
}

const CasinoTab = ({ currentUserId, chatId, initData }: CasinoTabProps) => {
  const [claimPoints, setClaimPoints] = useState<number | null>(null);
  const fetchedRef = useRef(false);

  useEffect(() => {
    if (fetchedRef.current) return;
    fetchedRef.current = true;

    ApiService.fetchUserProfile(currentUserId, chatId, initData)
      .then((result) => setClaimPoints(result.claim_balance))
      .catch(() => {/* badge will just show no balance */});
  }, [currentUserId, chatId, initData]);

  const updateClaimPoints = useCallback((count: number) => {
    setClaimPoints(count);
  }, []);

  const {
    symbols,
    spins,
    megaspin,
    loading,
    error,
    refetchSpins,
    updateSpins,
    updateMegaspin
  } = useSlots(chatId, currentUserId, initData);

  if (loading || symbols.length === 0 || claimPoints === null) {
    return <Loading message="Loading casino..." />;
  }

  if (error) {
    return (
      <div className="error-container">
        <h2>Error</h2>
        <p>{error}</p>
      </div>
    );
  }

  return (
    <Casino
      userId={currentUserId}
      chatId={chatId}
      initData={initData}
      slotsSymbols={symbols}
      slotsSpins={spins}
      slotsMegaspin={megaspin}
      refetchSpins={refetchSpins}
      updateSpins={updateSpins}
      updateMegaspin={updateMegaspin}
      claimPoints={claimPoints}
      updateClaimPoints={updateClaimPoints}
    />
  );
};

export default CasinoTab;
