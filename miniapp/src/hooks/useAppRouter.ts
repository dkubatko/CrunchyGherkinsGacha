import { useState, useEffect, useRef } from 'react';
import { TelegramUtils } from '../utils/telegram';

export type AppRoute = 
  | { type: 'loading' }
  | { type: 'error'; message: string }
  | { type: 'landing' }
  | { type: 'casino'; currentUserId: number; chatId: string; initData: string }
  | { type: 'singleCard'; currentUserId: number; cardId: number; initData: string }
  | { type: 'collection'; currentUserId: number; targetUserId: number; chatId: string | null; isOwnCollection: boolean; enableTrade: boolean; initData: string };

interface UseAppRouterResult {
  route: AppRoute;
}

/**
 * Hook that initializes the Telegram context and determines which view to render.
 * Parses the start_param from Telegram to route to the appropriate page.
 */
export const useAppRouter = (): UseAppRouterResult => {
  const [route, setRoute] = useState<AppRoute>({ type: 'loading' });
  const initializationStartedRef = useRef(false);

  useEffect(() => {
    if (initializationStartedRef.current) {
      return;
    }
    initializationStartedRef.current = true;

    const initialize = () => {
      try {
        // Check if this is a direct web access to root path (no Telegram context)
        const initData = TelegramUtils.getInitData();
        const isRootPath = window.location.pathname === '/' && 
                          !window.location.search && 
                          !window.location.hash;
        
        if (!initData && isRootPath) {
          // No Telegram context and on root path - show landing page
          setRoute({ type: 'landing' });
          return;
        }
        
        if (!initData) {
          // No Telegram context but not on root - redirect to landing page
          window.location.href = '/';
          return;
        }

        // Initialize user data from Telegram
        const userData = TelegramUtils.initializeUser();
        if (!userData) {
          // Has init data but failed to parse user - show error
          setRoute({ type: 'error', message: 'Failed to initialize user data' });
          return;
        }

        // Route based on the parsed userData
        if (userData.casinoView && userData.chatId) {
          setRoute({
            type: 'casino',
            currentUserId: userData.currentUserId,
            chatId: userData.chatId,
            initData
          });
        } else if (userData.singleCardView && userData.singleCardId) {
          setRoute({
            type: 'singleCard',
            currentUserId: userData.currentUserId,
            cardId: userData.singleCardId,
            initData
          });
        } else {
          setRoute({
            type: 'collection',
            currentUserId: userData.currentUserId,
            targetUserId: userData.targetUserId,
            chatId: userData.chatId ?? null,
            isOwnCollection: userData.isOwnCollection,
            enableTrade: userData.enableTrade,
            initData
          });
        }
      } catch (err) {
        const message = err instanceof Error ? err.message : 'An unknown error occurred';
        setRoute({ type: 'error', message });
      }
    };

    initialize();
  }, []);

  return { route };
};
