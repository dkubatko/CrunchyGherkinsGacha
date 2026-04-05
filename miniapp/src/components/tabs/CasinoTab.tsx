import { useState, useEffect, useRef } from 'react';
import { Casino } from '@/components/casino';
import Loading from '@/components/common/Loading';
import { useSlots } from '@/hooks';
import { ApiService } from '@/services/api';
import type { CasinoData } from '@/hooks/useHubData';

interface CasinoTabProps {
  currentUserId: number;
  chatId: string;
  initData: string;
  initialCasinoData?: CasinoData;
  claimPoints: number | null;
  onClaimPointsUpdate: (count: number) => void;
  currentSpinBalance?: number | null;
}

const CasinoTab = ({ currentUserId, chatId, initData, initialCasinoData, claimPoints, onClaimPointsUpdate, currentSpinBalance }: CasinoTabProps) => {
  const [rtbAvailable, setRtbAvailable] = useState<boolean | null>(initialCasinoData?.rtbAvailable ?? null);
  const [rtbUnavailableReason, setRtbUnavailableReason] = useState<string | null>(initialCasinoData?.rtbUnavailableReason ?? null);
  const fetchedRef = useRef(Boolean(initialCasinoData));

  useEffect(() => {
    if (fetchedRef.current) return;
    fetchedRef.current = true;

    Promise.all([
      ApiService.fetchUserProfile(currentUserId, chatId, initData),
      ApiService.getRTBConfig(initData, chatId),
    ]).then(([profile, rtbConfig]) => {
      onClaimPointsUpdate(profile.claim_balance);
      setRtbAvailable(rtbConfig.available);
      setRtbUnavailableReason(rtbConfig.unavailable_reason);
    }).catch(() => {/* badge will just show no balance */});
  }, [currentUserId, chatId, initData, onClaimPointsUpdate]);

  const slotsInitialData = initialCasinoData ? {
    symbols: initialCasinoData.symbols,
    spinsCount: initialCasinoData.spinsCount,
    megaspin: initialCasinoData.megaspin,
  } : undefined;

  const {
    symbols,
    spins,
    megaspin,
    loading,
    error,
    refetchSpins,
    updateSpins,
    updateMegaspin
  } = useSlots(chatId, currentUserId, initData, { initialData: slotsInitialData });

  // Sync spin balance from external updates (e.g., burning aspects in collection tab)
  useEffect(() => {
    if (currentSpinBalance != null) {
      updateSpins(currentSpinBalance);
    }
  }, [currentSpinBalance, updateSpins]);

  if (loading || symbols.length === 0 || claimPoints === null || rtbAvailable === null) {
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
      updateClaimPoints={onClaimPointsUpdate}
      rtbAvailable={rtbAvailable}
      rtbUnavailableReason={rtbUnavailableReason}
    />
  );
};

export default CasinoTab;
