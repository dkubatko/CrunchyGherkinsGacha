import React, { useState, useEffect, useCallback, useRef } from 'react';
import { AnimatePresence, motion } from 'framer-motion';
import { ApiService } from '@/services/api';
import { TelegramUtils } from '@/utils/telegram';
import { AppLoading } from '@/components/common';
import { CasinoHeader } from '@/components/casino';
import RTBCard from './RTBCard';
import { 
  cardContainerVariants, 
  isCardRevealed,
  generateCardIdentities,
  updateCardIdentityOnReveal,
  completeCardAnimation,
  getCardKey,
  splitByStack,
  type RTBCardIdentity,
} from '@/utils/rtbAnimations';
import type { RTBGameResponse, RTBConfigResponse, RTBCardInfo } from '@/types';
import './RideTheBus.css';

interface RideTheBusProps {
  chatId: string;
  initData: string;
  initialSpins?: number;
  onSpinsUpdate?: (count: number) => void;
}

type GamePhase = 'loading' | 'betting' | 'playing' | 'finished';

/** Animation phase for card reveal sequence */
type AnimationPhase = 'idle' | 'flipping' | 'moving';

/** Pending result from API during animation */
interface PendingGuessResult {
  game: RTBGameResponse;
  correct: boolean;
}

const RideTheBus: React.FC<RideTheBusProps> = ({ chatId, initData, initialSpins, onSpinsUpdate }) => {
  const [phase, setPhase] = useState<GamePhase>('loading');
  const [game, setGame] = useState<RTBGameResponse | null>(null);
  const [config, setConfig] = useState<RTBConfigResponse | null>(null);
  const [betAmount, setBetAmount] = useState<number>(10);
  const [spinsBalance, setSpinsBalance] = useState<number>(initialSpins ?? 0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [selectedCardIndex, setSelectedCardIndex] = useState<number | null>(null);
  const initializedRef = useRef(false);
  
  // Cooldown state - stores the end time for won/cashed_out games
  const [cooldownEndsAt, setCooldownEndsAt] = useState<Date | null>(null);
  const [cooldownRemaining, setCooldownRemaining] = useState<string | null>(null);
  
  // Animation state for card flip/move sequence
  const [animationPhase, setAnimationPhase] = useState<AnimationPhase>('idle');
  const [pendingResult, setPendingResult] = useState<PendingGuessResult | null>(null);
  const [flippingCardData, setFlippingCardData] = useState<RTBCardInfo | null>(null);
  
  // Unified card identity system - stable IDs throughout all animation phases
  // Initialized when game loads and updated as cards are revealed
  const [cardIdentities, setCardIdentities] = useState<RTBCardIdentity[]>([]);
  // Track which cards have completed their initial animation (to prevent re-pop-in)
  const [initializedCardIds, setInitializedCardIds] = useState<Set<string>>(new Set());

  const userId = TelegramUtils.initializeUser()?.currentUserId;

  // Initialize card identities when game loads or changes
  // This creates stable IDs for each card slot that persist through all phases
  useEffect(() => {
    if (!game || !config) return;
    
    const totalCards = config.cards_per_game;
    const revealedCardIds = game.cards
      .filter(c => isCardRevealed(c))
      .map(c => c.card_id);
    
    // Only regenerate if total cards changed (new game) or we have no identities
    if (cardIdentities.length !== totalCards) {
      const identities = generateCardIdentities(totalCards, revealedCardIds);
      setCardIdentities(identities);
      
      // Mark all revealed cards as already initialized (skip pop-in)
      const revealed = new Set(identities.filter(id => id.location === 'revealed').map(id => id.id));
      setInitializedCardIds(revealed);
    }
  }, [game, config, cardIdentities.length]);

  // Initialize: fetch config and check for existing game
  useEffect(() => {
    if (initializedRef.current || !userId) return;
    initializedRef.current = true;

    const initialize = async () => {
      try {
        setPhase('loading');
        
        // Fetch config and existing game in parallel
        const [configData, existingGame] = await Promise.all([
          ApiService.getRTBConfig(initData),
          ApiService.getRTBGame(userId, chatId, initData)
        ]);

        setConfig(configData);
        setBetAmount(configData.min_bet);

        if (existingGame) {
          setGame(existingGame);
          setSpinsBalance(existingGame.spins_balance ?? 0);
          onSpinsUpdate?.(existingGame.spins_balance ?? 0);
          
          // Check for cooldown (won/cashed_out games with cooldown_ends_at)
          if (existingGame.cooldown_ends_at) {
            const cooldownEnd = new Date(existingGame.cooldown_ends_at);
            if (cooldownEnd > new Date()) {
              setCooldownEndsAt(cooldownEnd);
              // Go to betting phase with cooldown active
              setPhase('betting');
              return;
            }
          }
          
          if (existingGame.status === 'active') {
            setPhase('playing');
          } else {
            setPhase('finished');
          }
        } else {
          // Fetch spins balance
          const spinsData = await ApiService.getUserSpins(userId, chatId, initData);
          setSpinsBalance(spinsData.spins);
          onSpinsUpdate?.(spinsData.spins);
          setPhase('betting');
        }
      } catch (err) {
        console.error('Failed to initialize RTB:', err);
        setError(err instanceof Error ? err.message : 'Failed to load game');
        setPhase('betting');
      }
    };

    initialize();
  }, [userId, chatId, initData, onSpinsUpdate]);

  // Update cooldown countdown timer
  useEffect(() => {
    if (!cooldownEndsAt) {
      setCooldownRemaining(null);
      return;
    }

    const updateCooldown = () => {
      const now = new Date();
      const diffMs = cooldownEndsAt.getTime() - now.getTime();

      if (diffMs <= 0) {
        // Cooldown expired
        setCooldownEndsAt(null);
        setCooldownRemaining(null);
        return;
      }

      const totalMinutes = Math.floor(diffMs / 1000 / 60);
      const hours = Math.floor(totalMinutes / 60);
      const minutes = totalMinutes % 60;

      if (hours >= 1) {
        setCooldownRemaining(`${hours}h ${minutes}m`);
      } else if (minutes >= 1) {
        setCooldownRemaining(`${minutes}m`);
      } else {
        setCooldownRemaining('<1m');
      }
    };

    // Update immediately
    updateCooldown();

    // Then update every minute (60 seconds)
    const interval = setInterval(updateCooldown, 60000);
    return () => clearInterval(interval);
  }, [cooldownEndsAt]);

  const handleStartGame = useCallback(async () => {
    if (!userId || !config) return;

    // Check if cooldown is still active
    if (cooldownEndsAt && cooldownEndsAt > new Date()) {
      TelegramUtils.triggerHapticNotification('error');
      return;
    }

    if (spinsBalance < betAmount) {
      TelegramUtils.triggerHapticNotification('error');
      return;
    }

    setLoading(true);
    try {
      const newGame = await ApiService.startRTBGame(userId, chatId, betAmount, initData);
      setGame(newGame);
      const newBalance = newGame.spins_balance ?? spinsBalance - betAmount;
      setSpinsBalance(newBalance);
      onSpinsUpdate?.(newBalance);
      setPhase('playing');
      TelegramUtils.triggerHapticNotification('success');
      // Clear any previous cooldown
      setCooldownEndsAt(null);
    } catch (err) {
      console.error('Failed to start game:', err);
      TelegramUtils.triggerHapticNotification('error');
    } finally {
      setLoading(false);
    }
  }, [userId, chatId, betAmount, spinsBalance, config, initData, cooldownEndsAt, onSpinsUpdate]);

  const handleGuess = useCallback(async (guess: 'higher' | 'lower' | 'equal') => {
    if (!userId || !game || animationPhase !== 'idle') return;

    setLoading(true);
    TelegramUtils.triggerHapticImpact('medium');
    
    try {
      const result = await ApiService.makeRTBGuess(userId, game.game_id, guess, initData);
      
      // Find the newly revealed card
      const currentRevealedIds = new Set(game.cards.filter(c => isCardRevealed(c)).map(c => c.card_id));
      const newCard = result.game.cards.find(c => isCardRevealed(c) && !currentRevealedIds.has(c.card_id));
      
      // Store result but DON'T apply yet - wait for animation
      setPendingResult({
        game: result.game,
        correct: result.correct,
      });
      setFlippingCardData(newCard || null);
      
      // Update card identity to 'animating' state (keeps same stable ID)
      if (newCard) {
        setCardIdentities(prev => updateCardIdentityOnReveal(prev, newCard.card_id, true));
      }
      
      // Start flip animation (effect handles timeout fallback)
      setAnimationPhase('flipping');
      
    } catch (err) {
      console.error('Failed to make guess:', err);
      TelegramUtils.triggerHapticNotification('error');
      setLoading(false);
    }
  }, [userId, game, animationPhase, initData]);

  // Called when the flip animation completes
  const handleFlipComplete = useCallback(() => {
    if (!pendingResult || animationPhase !== 'flipping') return;
    
    // Only transition to moving phase on correct guess (card moves from right to left stack)
    // On incorrect guess, skip directly to completion
    if (pendingResult.correct) {
      // DON'T apply game state yet - wait for move animation to complete
      // This prevents the card from appearing in left stack prematurely
      setAnimationPhase('moving');
    } else {
      // Fire haptic feedback for incorrect guess
      TelegramUtils.triggerHapticNotification('error');
      
      // For incorrect guess, delay game state update until finished phase
      // This prevents the card from appearing in the left stack
      setTimeout(() => {
        setGame(pendingResult.game);
        const newBalance = pendingResult.game.spins_balance ?? spinsBalance;
        setSpinsBalance(newBalance);
        onSpinsUpdate?.(newBalance);
        setPhase('finished');
        
        // Reset animation state
        setAnimationPhase('idle');
        setPendingResult(null);
        setFlippingCardData(null);
        setLoading(false);
      }, 500); // Brief delay to let user see the revealed card
    }
  }, [pendingResult, spinsBalance, animationPhase, onSpinsUpdate]);

  // Called when the layout/move animation completes (only fires on correct guess)
  const handleMoveComplete = useCallback(() => {
    if (!pendingResult || animationPhase !== 'moving') return;
    
    const gameOver = pendingResult.game.status !== 'active';
    
    // Fire haptic feedback for successful guess
    TelegramUtils.triggerHapticNotification('success');
    
    // Mark the animating card as fully revealed in identities
    setCardIdentities(prev => completeCardAnimation(prev));
    
    // Mark the newly revealed card as initialized (to skip pop-in on future repositions)
    if (flippingCardData) {
      const animatingIdentity = cardIdentities.find(id => id.cardId === flippingCardData.card_id);
      if (animatingIdentity) {
        setInitializedCardIds(prev => new Set([...prev, animatingIdentity.id]));
      }
    }
    
    // NOW apply game state - after animation is complete
    setGame(pendingResult.game);
    const newBalance = pendingResult.game.spins_balance ?? spinsBalance;
    setSpinsBalance(newBalance);
    onSpinsUpdate?.(newBalance);
    
    // Check for game over
    if (gameOver) {
      // Small delay before showing finished phase to let user see the result
      setTimeout(() => {
        setPhase('finished');
      }, 300);
    }
    
    // Reset animation state
    setAnimationPhase('idle');
    setPendingResult(null);
    setFlippingCardData(null);
    setLoading(false);
  }, [pendingResult, animationPhase, flippingCardData, cardIdentities, spinsBalance, onSpinsUpdate]);

  const handleCashOut = useCallback(async () => {
    if (!userId || !game) return;

    setLoading(true);
    TelegramUtils.triggerHapticImpact('heavy');
    
    try {
      const result = await ApiService.cashOutRTB(userId, game.game_id, initData);
      setSpinsBalance(result.new_spin_total);
      onSpinsUpdate?.(result.new_spin_total);
      // Use the game from the response which has the updated status
      setGame(result.game);
      setPhase('finished');
      TelegramUtils.triggerHapticNotification('success');
    } catch (err) {
      console.error('Failed to cash out:', err);
      TelegramUtils.triggerHapticNotification('error');
    } finally {
      setLoading(false);
    }
  }, [userId, game, initData, onSpinsUpdate]);

  const handleNewGame = useCallback(async () => {
    // Set phase first to hide multiplier before clearing game state
    setPhase('betting');
    setGame(null);
    setLoading(true);
    // Reset card identity system for new game
    setCardIdentities([]);
    setInitializedCardIds(new Set());
    
    if (!userId) {
      setLoading(false);
      return;
    }
    
    try {
      // Check if there's a cooldown by fetching existing game
      const [existingGame, spinsData] = await Promise.all([
        ApiService.getRTBGame(userId, chatId, initData),
        ApiService.getUserSpins(userId, chatId, initData)
      ]);
      
      setSpinsBalance(spinsData.spins);
      onSpinsUpdate?.(spinsData.spins);
      
      if (existingGame?.cooldown_ends_at) {
        const cooldownEnd = new Date(existingGame.cooldown_ends_at);
        if (cooldownEnd > new Date()) {
          setCooldownEndsAt(cooldownEnd);
        }
      }
      
      setPhase('betting');
    } catch (err) {
      console.error('Failed to check for new game:', err);
      setPhase('betting');
    } finally {
      setLoading(false);
    }
  }, [userId, chatId, initData, onSpinsUpdate]);

  if (phase === 'loading') {
    return <AppLoading title="🚌 Ride the Bus" spinsCount={spinsBalance} />;
  }

  if (error && !game) {
    return (
      <div className="rtb-container">
        <div className="rtb-error">
          <p>{error}</p>
          <button onClick={() => window.location.reload()}>Retry</button>
        </div>
      </div>
    );
  }

  const renderCards = () => {
    const cards = game?.cards || [];
    const totalCards = config?.cards_per_game || 5;

    // Create placeholder cards for betting phase
    const createPlaceholderCard = (index: number): RTBCardInfo => ({
      card_id: index,
      rarity: '???',
      title: '',
      image_b64: null,
    });

    // Betting phase: show all 5 placeholder cards in arc layout
    if (phase === 'betting' || !game) {
      const placeholderCards = Array.from({ length: totalCards }, (_, i) => createPlaceholderCard(i));
      
      return (
        <div className="rtb-cards-game-layout rtb-cards-finished">
          <motion.div 
            className="rtb-cards-arc"
            variants={cardContainerVariants}
            initial="hidden"
            animate="visible"
          >
            <AnimatePresence mode="popLayout">
              {placeholderCards.map((card, index) => (
                <RTBCard
                  key={`betting-${index}`}
                  card={card}
                  cardId={`betting-${index}`}
                  variant="arc"
                  index={index}
                  total={totalCards}
                  isRevealed={false}
                  zIndex={index + 1}
                />
              ))}
            </AnimatePresence>
          </motion.div>
        </div>
      );
    }

    // Finished phase: show cards in an arc layout, clickable to inspect in-place
    if (phase === 'finished') {
      const revealedCards = cards.filter(card => card && isCardRevealed(card));
      const isLostGame = game?.status === 'lost';
      const losingCardIndex = isLostGame ? revealedCards.length - 1 : -1;
      
      return (
        <div 
          className="rtb-cards-game-layout rtb-cards-finished"
          onClick={() => setSelectedCardIndex(null)}
        >
          <motion.div 
            className="rtb-cards-arc"
            variants={cardContainerVariants}
            initial="hidden"
            animate="visible"
          >
            <AnimatePresence mode="popLayout">
              {revealedCards.map((card, index) => {
                const isSelected = selectedCardIndex === index;
                const isLosingCard = index === losingCardIndex;
                
                return (
                  <RTBCard
                    key={`finished-${card.card_id}`}
                    card={card}
                    cardId={card.card_id}
                    variant="arc"
                    index={index}
                    total={revealedCards.length}
                    isRevealed={true}
                    isSelected={isSelected}
                    isLosing={isLosingCard}
                    zIndex={isSelected ? 100 : index + 1}
                    onClick={(e) => {
                      e?.stopPropagation();
                      setSelectedCardIndex(isSelected ? null : index);
                      TelegramUtils.triggerHapticSelection();
                    }}
                  />
                );
              })}
            </AnimatePresence>
          </motion.div>
        </div>
      );
    }

    // Active gameplay: All cards rendered in a single container with absolute positioning
    // This ensures smooth cross-stack animations with proper z-index layering
    
    // Split card identities by stack location for position calculation
    const { leftStack, rightStack, animatingCard } = splitByStack(cardIdentities);
    
    // Build a map of card_id to card data for quick lookup
    const cardDataMap = new Map(cards.map(c => [c.card_id, c]));
    
    // Calculate z-index for a card based on its location and animation state
    const getCardZIndex = (identity: RTBCardIdentity, stackIndex: number): number => {
      // Animating cards always on top
      if (identity.location === 'animating') {
        return 100;
      }
      // Left stack: higher index = higher z-index (top card on top)
      if (identity.location === 'revealed') {
        return 10 + stackIndex;
      }
      // Right stack: lower index = higher z-index (top card on top)
      // rightStack[0] is the top card (next to reveal)
      return 10 + (rightStack.length - stackIndex);
    };

    return (
      <div className="rtb-cards-game-layout">
        {/* Single unified container for all cards - enables cross-stack layout animations */}
        <div className="rtb-cards-unified">
          <AnimatePresence mode="popLayout">
            {/* Render LEFT STACK cards (revealed) */}
            {leftStack.map((identity, stackIndex) => {
              const cardData = identity.cardId ? cardDataMap.get(identity.cardId) : null;
              if (!cardData) return null;
              
              const isTop = stackIndex === leftStack.length - 1;
              const key = getCardKey(identity);
              const skipInitial = initializedCardIds.has(identity.id);
              // Account for animating card in total when it's moving to left stack
              const totalInLeftStack = leftStack.length + (animationPhase === 'moving' ? 1 : 0);
              
              return (
                <RTBCard
                  key={key}
                  card={cardData}
                  cardId={identity.id}
                  variant="stackLeft"
                  index={stackIndex}
                  total={totalInLeftStack}
                  isRevealed={true}
                  isTop={isTop && animationPhase === 'idle'}
                  skipInitialAnimation={skipInitial}
                  useAbsolutePosition={true}
                  zIndex={getCardZIndex(identity, stackIndex)}
                />
              );
            })}
            
            {/* Render RIGHT STACK cards (unrevealed) */}
            {rightStack.map((identity, stackIndex) => {
              const placeholderCard = createPlaceholderCard(identity.slotIndex);
              const key = getCardKey(identity);
              const skipInitial = initializedCardIds.has(identity.id);
              // Account for animating card in total when it's flipping on right stack
              const totalInRightStack = rightStack.length + (animationPhase === 'flipping' ? 1 : 0);
              // During flip phase, shift indices down by 1 since flipping card is at index 0
              const adjustedIndex = animationPhase === 'flipping' ? stackIndex + 1 : stackIndex;
              
              return (
                <RTBCard
                  key={key}
                  card={placeholderCard}
                  cardId={identity.id}
                  variant="stackRight"
                  index={adjustedIndex}
                  total={totalInRightStack}
                  isRevealed={false}
                  skipInitialAnimation={skipInitial}
                  useAbsolutePosition={true}
                  zIndex={getCardZIndex(identity, stackIndex)}
                />
              );
            })}
            
            {/* Render ANIMATING card (flipping or moving) */}
            {/* This card uses the same stable key/layoutId throughout both phases */}
            {(animationPhase === 'flipping' || animationPhase === 'moving') && 
              flippingCardData && animatingCard && (
              <RTBCard
                key={getCardKey(animatingCard)}
                card={flippingCardData}
                cardId={animatingCard.id}
                variant={animationPhase === 'moving' ? 'stackLeft' : 'stackRight'}
                initialVariant={animationPhase === 'moving' ? 'stackRight' : undefined}
                index={animationPhase === 'moving' ? leftStack.length : 0}
                total={animationPhase === 'moving' ? leftStack.length + 1 : rightStack.length + 1}
                initialIndex={animationPhase === 'moving' ? 0 : undefined}
                initialTotal={animationPhase === 'moving' ? rightStack.length + 1 : undefined}
                isRevealed={animationPhase === 'moving'}
                isFlipping={animationPhase === 'flipping'}
                isTop={animationPhase === 'moving'}
                skipInitialAnimation={animationPhase === 'moving'}
                useAbsolutePosition={true}
                zIndex={100}
                onFlipComplete={animationPhase === 'flipping' ? handleFlipComplete : undefined}
                onLayoutAnimationComplete={animationPhase === 'moving' ? handleMoveComplete : undefined}
              />
            )}
          </AnimatePresence>
        </div>
      </div>
    );
  };

  const renderMultiplier = () => {
    const currentMultiplier = game?.current_multiplier ?? 1;
    const potentialPayout = game?.potential_payout ?? betAmount;

    // Determine multiplier tier for styling
    let multiplierTier = 'low';
    if (currentMultiplier >= 5) multiplierTier = 'extreme';
    else if (currentMultiplier >= 3) multiplierTier = 'high';
    else if (currentMultiplier >= 2) multiplierTier = 'medium';

    let statusText: React.ReactNode = '';
    let statusClass = '';
    
    if (game?.status === 'won') {
      statusText = <span>Won <span className="rtb-coin-inline"></span> {potentialPayout}</span>;
      statusClass = 'win';
    } else if (game?.status === 'lost') {
      statusText = <span>Lost <span className="rtb-coin-inline"></span> {game.bet_amount}</span>;
      statusClass = 'lose';
    } else if (game?.status === 'cashed_out') {
      statusText = <span>Cashed out <span className="rtb-coin-inline"></span> {potentialPayout}</span>;
      statusClass = 'cashout';
    }

    return (
      <div className="rtb-multiplier-container">
        <span className={`rtb-multiplier rtb-multiplier-${multiplierTier}`}>{currentMultiplier}x</span>
        {statusText ? (
          <span className={`rtb-status ${statusClass}`}>{statusText}</span>
        ) : game?.status === 'active' ? (
          <span className="rtb-payout"><span className="rtb-coin-inline"></span> {potentialPayout}</span>
        ) : null}
      </div>
    );
  };

  const renderBettingControls = () => {
    if (!config) return null;

    const betOptions = [10, 20, 30];
    const isOnCooldown = !!(cooldownEndsAt && cooldownEndsAt > new Date());

    return (
      <div className="rtb-betting-container">
        <div className="rtb-bet-buttons">
          {betOptions.map((amount) => (
            <button
              key={amount}
              className={`rtb-bet-option ${betAmount === amount ? 'selected' : ''}`}
              onClick={() => {
                if (amount <= spinsBalance && !isOnCooldown) {
                  setBetAmount(amount);
                  TelegramUtils.triggerHapticSelection();
                }
              }}
              disabled={amount > spinsBalance || isOnCooldown}
            >
              <span className="rtb-coin-inline"></span> {amount}
            </button>
          ))}
        </div>

        <button
          className="rtb-start-button"
          onClick={handleStartGame}
          disabled={loading || spinsBalance < betAmount || isOnCooldown}
        >
          {loading ? 'Loading...' : isOnCooldown ? (cooldownRemaining ? `Next game in ${cooldownRemaining}` : 'Loading...') : 'PLAY'}
        </button>
      </div>
    );
  };

  const renderGameControls = () => {
    if (!game || game.status !== 'active') return null;

    const canCashOut = game.current_position >= 2;
    const isDisabled = loading;

    return (
      <div className="rtb-game-controls">
        <div className="rtb-guess-buttons">
          <button
            className="rtb-guess-button higher"
            onClick={() => handleGuess('higher')}
            disabled={isDisabled}
          >
            Higher
          </button>
          <button
            className="rtb-guess-button equal"
            onClick={() => handleGuess('equal')}
            disabled={isDisabled}
          >
            Equal
          </button>
          <button
            className="rtb-guess-button lower"
            onClick={() => handleGuess('lower')}
            disabled={isDisabled}
          >
            Lower
          </button>
        </div>
        
        <button
          className={`rtb-cashout-button ${!canCashOut ? 'disabled' : ''}`}
          onClick={handleCashOut}
          disabled={isDisabled || !canCashOut}
        >
          Cash Out
        </button>
      </div>
    );
  };

  const renderFinishedControls = () => {
    if (phase !== 'finished') return null;

    return (
      <div className="rtb-finished-controls">
        <button
          className="rtb-new-game-button"
          onClick={handleNewGame}
        >
          Play Again
        </button>
      </div>
    );
  };

  return (
    <div 
      className="rtb-container"
      onClick={() => {
        if (selectedCardIndex !== null) {
          setSelectedCardIndex(null);
        }
      }}
    >
      <CasinoHeader title="🚌 Ride the Bus" spinsCount={spinsBalance} />

      {renderCards()}
      {(phase === 'playing' || phase === 'finished') && renderMultiplier()}

      {phase === 'betting' && renderBettingControls()}
      {phase === 'playing' && renderGameControls()}
      {phase === 'finished' && renderFinishedControls()}
    </div>
  );
};

export default RideTheBus;
