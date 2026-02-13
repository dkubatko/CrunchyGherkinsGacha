import { Casino } from '@/components/casino';
import Loading from '@/components/common/Loading';
import { useSlots } from '@/hooks';

interface CasinoTabProps {
  currentUserId: number;
  chatId: string;
  initData: string;
}

const CasinoTab = ({ currentUserId, chatId, initData }: CasinoTabProps) => {
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

  if (loading || symbols.length === 0) {
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
    />
  );
};

export default CasinoTab;
