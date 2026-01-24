import { useEffect } from 'react';
import { Casino } from '@/components/casino';
import { Title, SpinsBadge } from '@/components/common';
import { useSlots } from '@/hooks';
import { TelegramUtils } from '@/utils/telegram';
import '@/App.css';

interface CasinoPageProps {
  currentUserId: number;
  chatId: string;
  initData: string;
}

export const CasinoPage = ({ currentUserId, chatId, initData }: CasinoPageProps) => {
  const {
    symbols,
    spins,
    megaspin,
    loading,
    error,
    refetchSpins,
    updateSpins,
    updateMegaspin
  } = useSlots(chatId, currentUserId);

  // Expand app on mount
  useEffect(() => {
    TelegramUtils.expandApp();
  }, []);

  // Loading state for casino
  if (loading || symbols.length === 0) {
    return (
      <div className="app-container">
        <Title title="🎰 Casino" rightContent={<SpinsBadge count={spins.count} />} fullscreen />
      </div>
    );
  }

  // Error state
  if (error) {
    return (
      <div className="app-container">
        <h1>Error: {error}</h1>
      </div>
    );
  }

  return (
    <div className="app-container">
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
    </div>
  );
};
