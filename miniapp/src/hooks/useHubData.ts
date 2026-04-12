import { useState, useEffect, useRef, useCallback } from 'react';
import { ApiService } from '@/services/api';
import { cardsCache } from '@/lib/cardsCache';
import { aspectsCache } from '@/lib/aspectsCache';
import type {
  CardData,
  AspectData,
  UserProfile,
  AspectConfigResponse,
} from '@/types';

// Mirrors SlotSymbol from useSlots
export interface SlotSymbol {
  id: number;
  iconb64?: string;
  displayName?: string;
  type: 'user' | 'character' | 'claim' | 'set';
}

export interface CasinoData {
  symbols: SlotSymbol[];
  spinsCount: number;
  megaspin: {
    spinsUntilMegaspin: number;
    totalSpinsRequired: number;
    megaspinAvailable: boolean;
  };
  claimPoints: number;
  rtbAvailable: boolean;
  rtbUnavailableReason: string | null;
}

export interface CollectionData {
  cards: CardData[];
  userId: number;
  isOwnCollection: boolean;
  enableTrade: boolean;
}

export interface HubData {
  profile: UserProfile | null;
  profileError: string | null;
  collection: CollectionData | null;
  collectionError: string | null;
  aspects: AspectData[];
  aspectsError: string | null;
  allCards: CardData[];
  allCardsError: string | null;
  allChatAspects: AspectData[];
  allChatAspectsError: string | null;
  casino: CasinoData | null;
  casinoError: string | null;
  config: AspectConfigResponse | null;
  configError: string | null;
  ready: boolean;
  progress: number;
  refreshProfile: () => Promise<void>;
  // Client-side update functions for AllTab reactivity
  updateCardInAll: (cardId: number, updates: Partial<CardData>) => void;
  removeCardFromAll: (cardId: number) => void;
  updateAspectInAll: (aspectId: number, updates: Partial<AspectData>) => void;
  removeAspectFromAll: (aspectId: number) => void;
  // Shared claim points state (updated by lock ops in Collection and wins in Casino)
  claimPoints: number | null;
  updateClaimPoints: (count: number) => void;
}

interface UseHubDataParams {
  currentUserId: number;
  targetUserId: number;
  chatId: string | null;
  initData: string;
}

export const useHubData = ({
  currentUserId,
  targetUserId,
  chatId,
  initData,
}: UseHubDataParams): HubData => {
  const [profile, setProfile] = useState<UserProfile | null>(null);
  const [profileError, setProfileError] = useState<string | null>(null);

  const [collection, setCollection] = useState<CollectionData | null>(null);
  const [collectionError, setCollectionError] = useState<string | null>(null);

  const [aspects, setAspects] = useState<AspectData[]>([]);
  const [aspectsError, setAspectsError] = useState<string | null>(null);

  const [allCards, setAllCards] = useState<CardData[]>([]);
  const [allCardsError, setAllCardsError] = useState<string | null>(null);

  const [allChatAspects, setAllChatAspects] = useState<AspectData[]>([]);
  const [allChatAspectsError, setAllChatAspectsError] = useState<string | null>(null);

  const [casino, setCasino] = useState<CasinoData | null>(null);
  const [casinoError, setCasinoError] = useState<string | null>(null);

  // Shared claim points — updated by lock operations in Collection and claim wins in Casino
  const [claimPoints, setClaimPoints] = useState<number | null>(null);

  const [config, setConfig] = useState<AspectConfigResponse | null>(null);
  const [configError, setConfigError] = useState<string | null>(null);

  const [ready, setReady] = useState(false);
  const [progress, setProgress] = useState(0);

  // Capture initial params in refs so the fetch effect can use [] deps honestly.
  // These come from the router and are stable for the component's lifetime.
  const paramsRef = useRef({ currentUserId, targetUserId, chatId, initData });

  const refreshProfile = useCallback(async () => {
    if (!chatId) return;
    try {
      const isOwnCollection = currentUserId === targetUserId;
      const profileUserId = isOwnCollection ? currentUserId : targetUserId;
      const result = await ApiService.fetchUserProfile(profileUserId, chatId, initData);
      setProfile(result);
    } catch {
      // Silent refresh failure — keep existing data
    }
  }, [currentUserId, targetUserId, chatId, initData]);

  useEffect(() => {
    const { currentUserId, targetUserId, chatId, initData } = paramsRef.current;

    const fetchAll = async () => {
      const isOwnCollection = currentUserId === targetUserId;
      const profileUserId = isOwnCollection ? currentUserId : targetUserId;

      // Determine total number of fetches for progress tracking
      // With chatId: 8 fetches (profile, cards, aspects, allCards, allChatAspects, slots, casino meta, config)
      // Without chatId: 3 fetches (cards, aspects, config)
      const totalFetches = chatId ? 8 : 3;
      let completedFetches = 0;

      const incrementProgress = () => {
        completedFetches++;
        setProgress(completedFetches / totalFetches);
      };

      // --- Always fetch user's collection cards + aspects + config ---
      const cardsPromise = ApiService.fetchUserCards(targetUserId, initData, chatId ?? undefined)
        .then(result => {
          const responseUserId = result.user_id;
          const isOwn = responseUserId === currentUserId;
          setCollection({
            cards: result.cards,
            userId: responseUserId,
            isOwnCollection: isOwn,
            enableTrade: isOwn,
          });
          incrementProgress();
          return result;
        })
        .catch(err => {
          setCollectionError(err?.message ?? 'Failed to load cards');
          incrementProgress();
          return null;
        });

      const aspectsPromise = ApiService.fetchUserAspects(initData, chatId, targetUserId)
        .then(result => {
          setAspects(result);
          incrementProgress();
          return result;
        })
        .catch(err => {
          setAspectsError(err?.message ?? 'Failed to load aspects');
          incrementProgress();
          return [];
        });

      const configPromise = ApiService.fetchAspectConfig(initData)
        .then(result => {
          setConfig(result);
          incrementProgress();
          return result;
        })
        .catch(err => {
          setConfigError(err?.message ?? 'Failed to load config');
          incrementProgress();
          return null;
        });

      // --- Conditionally fetch chat-scoped data (requires chatId) ---
      if (chatId) {
        // Profile — store result for casino to use
        const profilePromise = ApiService.fetchUserProfile(profileUserId, chatId, initData)
          .then(result => {
            setProfile(result);
            incrementProgress();
            return result;
          })
          .catch(err => {
            setProfileError(err?.message ?? 'Failed to load profile');
            incrementProgress();
            return null;
          });

        // All cards in chat
        const allCardsPromise = ApiService.fetchAllCards(initData, chatId)
          .then(result => {
            setAllCards(result);
            cardsCache.set(result, initData, chatId);
            incrementProgress();
          })
          .catch(err => {
            setAllCardsError(err?.message ?? 'Failed to load all cards');
            incrementProgress();
          });

        // All aspects in chat
        const allAspectsPromise = ApiService.fetchAllChatAspects(initData, chatId)
          .then(result => {
            setAllChatAspects(result);
            aspectsCache.set(result, initData, chatId);
            incrementProgress();
          })
          .catch(err => {
            setAllChatAspectsError(err?.message ?? 'Failed to load all aspects');
            incrementProgress();
          });

        // Slot symbols + casino meta
        const casinoPromise = (async () => {
          // Fetch symbols first
          let symbols: SlotSymbol[] = [];
          try {
            const [symbolsData, setSymbolsData] = await Promise.all([
              ApiService.fetchSlotSymbols(chatId, initData),
              ApiService.getSetSymbols(chatId, initData),
            ]);
            const allSymbolsData = [...symbolsData, ...setSymbolsData];
            symbols = allSymbolsData
              .filter(item => item.slot_icon_b64)
              .map(item => ({
                id: item.id,
                iconb64: item.slot_icon_b64 || undefined,
                displayName: item.display_name || `${item.type} ${item.id}`,
                type: item.type,
              }));
            // Ensure at least 3 symbols for the slot machine
            while (symbols.length < 3) {
              symbols.push(
                ...symbols.slice(0, Math.min(3 - symbols.length, symbols.length))
              );
            }
          } catch {
            // Symbols failed, continue with empty
          }
          incrementProgress();

          // Fetch casino meta (spins + RTB config)
          try {
            // Wait for profile to be fetched so we can get claim balance
            const resolvedProfile = await profilePromise;

            const [spinsData, rtbConfig] = await Promise.all([
              ApiService.getUserSpins(currentUserId, chatId, initData),
              ApiService.getRTBConfig(initData, chatId),
            ]);

            const fetchedClaimPoints = resolvedProfile?.claim_balance ?? 0;
            setCasino({
              symbols,
              spinsCount: spinsData.spins,
              megaspin: {
                spinsUntilMegaspin: spinsData.megaspin?.spins_until_megaspin ?? 100,
                totalSpinsRequired: spinsData.megaspin?.total_spins_required ?? 100,
                megaspinAvailable: spinsData.megaspin?.megaspin_available ?? false,
              },
              claimPoints: fetchedClaimPoints,
              rtbAvailable: rtbConfig.available,
              rtbUnavailableReason: rtbConfig.unavailable_reason,
            });
            setClaimPoints(fetchedClaimPoints);
          } catch (err: unknown) {
            const error = err as Error | null;
            setCasinoError(error?.message ?? 'Failed to load casino');
          }
          incrementProgress();
        })();

        // Wait for ALL chat fetches to complete
        await Promise.all([profilePromise, allCardsPromise, allAspectsPromise, casinoPromise]);
      }

      // Wait for base fetches to complete before marking ready
      await Promise.all([cardsPromise, aspectsPromise, configPromise]);

      setReady(true);
    };

    fetchAll();
  }, []);

  // Client-side update functions for AllTab reactivity (no API calls)
  const updateCardInAll = useCallback((cardId: number, updates: Partial<CardData>) => {
    setAllCards(prev => prev.map(c => c.id === cardId ? { ...c, ...updates } : c));
  }, []);

  const removeCardFromAll = useCallback((cardId: number) => {
    setAllCards(prev => prev.filter(c => c.id !== cardId));
  }, []);

  const updateAspectInAll = useCallback((aspectId: number, updates: Partial<AspectData>) => {
    setAllChatAspects(prev => prev.map(a => a.id === aspectId ? { ...a, ...updates } : a));
  }, []);

  const removeAspectFromAll = useCallback((aspectId: number) => {
    setAllChatAspects(prev => prev.filter(a => a.id !== aspectId));
  }, []);

  const updateClaimPoints = useCallback((count: number) => {
    setClaimPoints(count);
  }, []);

  return {
    profile,
    profileError,
    collection,
    collectionError,
    aspects,
    aspectsError,
    allCards,
    allCardsError,
    allChatAspects,
    allChatAspectsError,
    casino,
    casinoError,
    config,
    configError,
    ready,
    progress,
    refreshProfile,
    updateCardInAll,
    removeCardFromAll,
    updateAspectInAll,
    removeAspectFromAll,
    claimPoints,
    updateClaimPoints,
  };
};
