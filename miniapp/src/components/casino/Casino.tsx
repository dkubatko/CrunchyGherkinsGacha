import { useState, useEffect, useRef } from 'react';
import './Casino.css';
import { Title, SpinsBadge } from '@/components/common';
import Slots from './slots/Slots';
import Minesweeper from './minesweeper/Minesweeper';
import RideTheBus from './rtb/RideTheBus';
import { ApiService } from '@/services/api';
import { TelegramUtils } from '@/utils/telegram';
import slotsCover from '@/assets/casino/slots_cover.webp';
import minesweeperCover from '@/assets/casino/minesweeper_cover.webp';
import rtbCover from '@/assets/casino/rtb_cover.webp';

interface SlotSymbol {
  id: number;
  display_name?: string | null;
  slot_iconb64?: string | null;
  type: 'user' | 'character' | 'claim';
}

interface UserSpinsData {
  count: number;
  loading: boolean;
  error: string | null;
  nextRefreshTime?: string | null;
}

interface MegaspinData {
  spinsUntilMegaspin: number;
  totalSpinsRequired: number;
  megaspinAvailable: boolean;
  loading: boolean;
  error: string | null;
}

interface MegaspinInfo {
  spins_until_megaspin: number;
  total_spins_required: number;
  megaspin_available: boolean;
}

interface CasinoProps {
  userId: number;
  chatId: string;
  initData: string;
  slotsSymbols: SlotSymbol[];
  slotsSpins: UserSpinsData;
  slotsMegaspin: MegaspinData;
  refetchSpins: () => Promise<void>;
  updateSpins: (count: number, nextRefreshTime?: string | null) => void;
  updateMegaspin: (megaspinInfo: MegaspinInfo) => void;
}

type GameView = 'catalog' | 'slots' | 'minesweeper' | 'ridethebus';

type GameInfo = {
  title: string;
  description: string;
  rules: string[];
};

const GAME_INFO: Record<'slots' | 'minesweeper' | 'ridethebus', GameInfo> = {
  slots: {
    title: 'Slots',
    description: 'Spin the reels to win cards!',
    rules: [
      'Match 3 symbols to win a card',
      'You get 5 spins ever 3 hours',
      'Burn cards to get more spins!'
    ]
  },
  minesweeper: {
    title: 'Minesweeper',
    description: 'Bet a card & clear the board to win!',
    rules: [
      'Select a card to bet to set reward rarity',
      'Reveal three symbols to win a card',
      'Reveal a bomb and lose your bet card!'
    ]
  },
  ridethebus: {
    title: 'Ride the Bus',
    description: 'Guess card rarities to multiply your spins!',
    rules: [
      'Bet 10, 20 or 30 spins to start',
      'Guess the next card\'s rarity',
      'Multiplier goes 2x → 3x → 5x → 10x',
      'Cash out anytime or ride to the end!'
    ]
  }
};

export default function Casino({
  userId,
  chatId,
  initData,
  slotsSymbols,
  slotsSpins,
  slotsMegaspin,
  refetchSpins,
  updateSpins,
  updateMegaspin
}: CasinoProps) {
  const [currentView, setCurrentView] = useState<GameView>('catalog');
  const [showInfo, setShowInfo] = useState<'slots' | 'minesweeper' | 'ridethebus' | null>(null);
  const [rtbAvailable, setRtbAvailable] = useState<boolean>(true);
  const [rtbUnavailableReason, setRtbUnavailableReason] = useState<string | null>(null);
  const rtbCheckRef = useRef(false);

  // Check RTB availability on mount
  useEffect(() => {
    if (rtbCheckRef.current) return;
    rtbCheckRef.current = true;

    ApiService.getRTBConfig(initData, chatId)
      .then((config) => {
        setRtbAvailable(config.available);
        setRtbUnavailableReason(config.unavailable_reason);
      })
      .catch((err) => {
        console.error('Failed to check RTB availability:', err);
      });
  }, [initData, chatId]);

  // Setup back button when viewing a game
  useEffect(() => {
    if (currentView === 'catalog') {
      TelegramUtils.hideBackButton();
      return;
    }

    const cleanup = TelegramUtils.setupBackButton(() => {
      setCurrentView('catalog');
    });

    return cleanup;
  }, [currentView]);

  const handleGameSelect = (game: 'slots' | 'minesweeper' | 'ridethebus') => {
    TelegramUtils.triggerHapticSelection();
    setCurrentView(game);
  };

  const handleInfoClick = (e: React.MouseEvent, game: 'slots' | 'minesweeper' | 'ridethebus') => {
    e.stopPropagation(); // Prevent card click
    TelegramUtils.triggerHapticImpact('light');
    setShowInfo(game);
  };

  const handleCloseInfo = () => {
    setShowInfo(null);
  };

  // Render game views
  if (currentView === 'slots') {
    return (
      <Slots
        symbols={slotsSymbols}
        spins={slotsSpins}
        megaspin={slotsMegaspin}
        userId={userId}
        chatId={chatId}
        initData={initData}
        refetchSpins={refetchSpins}
        onSpinsUpdate={updateSpins}
        onMegaspinUpdate={updateMegaspin}
      />
    );
  }

  if (currentView === 'minesweeper') {
    return (
      <Minesweeper
        chatId={chatId}
        initData={initData}
      />
    );
  }

  if (currentView === 'ridethebus') {
    return (
      <RideTheBus
        chatId={chatId}
        initData={initData}
        initialSpins={slotsSpins.count}
        onSpinsUpdate={(count) => updateSpins(count)}
      />
    );
  }

  // Catalog view
  return (
    <div className="casino-catalog-container">
      <Title title="🎰 Casino" rightContent={<SpinsBadge count={slotsSpins.count} />} />
      <div className="casino-games-grid">
          <div 
            className="casino-game-card"
            onClick={() => handleGameSelect('slots')}
          >
            <img src={slotsCover} alt="Slots" className="casino-game-image" />
            <button 
              className="casino-info-icon"
              onClick={(e) => handleInfoClick(e, 'slots')}
              aria-label="Slots info"
            >
              i
            </button>
            <div className="casino-game-info">
              <div className="casino-game-name">Slots</div>
              <div className="casino-game-description">Spin to win</div>
            </div>
          </div>
          
          <div 
            className="casino-game-card"
            onClick={() => handleGameSelect('minesweeper')}
          >
            <img src={minesweeperCover} alt="Minesweeper" className="casino-game-image" />
            <button 
              className="casino-info-icon"
              onClick={(e) => handleInfoClick(e, 'minesweeper')}
              aria-label="Minesweeper info"
            >
              i
            </button>
            <div className="casino-game-info">
              <div className="casino-game-name">Minesweeper</div>
              <div className="casino-game-description">Clear the board</div>
            </div>
          </div>
          
          <div 
            className={`casino-game-card ${!rtbAvailable ? 'locked' : ''}`}
            onClick={() => rtbAvailable && handleGameSelect('ridethebus')}
          >
            <img src={rtbCover} alt="Ride the Bus" className="casino-game-image" />
            {!rtbAvailable && (
              <div className="casino-game-locked-overlay">
                <span className="casino-game-locked-icon">🔒</span>
                <span className="casino-game-locked-text">
                  {rtbUnavailableReason || 'Unavailable'}
                </span>
              </div>
            )}
            <button 
              className="casino-info-icon"
              onClick={(e) => handleInfoClick(e, 'ridethebus')}
              aria-label="Ride the Bus info"
            >
              i
            </button>
            <div className="casino-game-info">
              <div className="casino-game-name">Ride the Bus</div>
              <div className="casino-game-description">Guess & multiply</div>
            </div>
          </div>
        </div>

      {/* Info Popup */}
      {showInfo && (
        <div className="casino-info-overlay" onClick={handleCloseInfo}>
          <div className="casino-info-popup" onClick={(e) => e.stopPropagation()}>
            <div className="casino-info-header">
              <h2>{GAME_INFO[showInfo].title}</h2>
              <button className="casino-info-close" onClick={handleCloseInfo}>✕</button>
            </div>
            <p className="casino-info-description">{GAME_INFO[showInfo].description}</p>
            <div className="casino-info-rules">
              <h3>How to Play:</h3>
              <ul>
                {GAME_INFO[showInfo].rules.map((rule, index) => (
                  <li key={index}>{rule}</li>
                ))}
              </ul>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
