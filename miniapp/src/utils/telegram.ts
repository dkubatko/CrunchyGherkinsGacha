import WebApp from '@twa-dev/sdk';
import type { UserData, OrientationData } from '../types';

type ParsedPayload =
  | { kind: 'card'; cardId: number }
  | { kind: 'user'; userId: number }
  | { kind: 'userChat'; userId: number; chatId: string }
  | { kind: 'casino'; chatId: string };

export class TelegramUtils {
  private static readonly TOKEN_PREFIX = 'tg1_';

  // Token format documentation:
  // Supported external payload (start_param) values after the optional tg1_ base64 wrapper:
  //   c-<cardId>                     => Single card view (display only this card)
  //   u-<userId>                     => View user collection
  //   uc-<userId>-<chatId>           => View user collection scoped to chat
  //   casino-<chatId>                 => Open casino catalog with game selection
  // Unrecognized payloads are ignored.

  static decodeToken(token: string): string | null {
    if (!token.startsWith(TelegramUtils.TOKEN_PREFIX)) {
      return null;
    }

    const raw = token.slice(TelegramUtils.TOKEN_PREFIX.length);
    if (!raw) {
      return null;
    }

    const normalized = raw.replace(/-/g, '+').replace(/_/g, '/');
    const padLength = normalized.length % 4;
    const padded = padLength ? normalized + '='.repeat(4 - padLength) : normalized;

    try {
      const binary = atob(padded);
      const bytes = Uint8Array.from(binary, (char) => char.charCodeAt(0));
      const decoder = new TextDecoder();
      return decoder.decode(bytes);
    } catch (err) {
      console.error('Failed to decode token payload', err);
      return null;
    }
  }

  private static parsePayload(payload: string): ParsedPayload | null {
    const trimmed = payload.trim();
    if (!trimmed) {
      return null;
    }

    const lower = trimmed.toLowerCase();

    if (lower.startsWith('c-')) {
      const maybeCardId = Number(trimmed.slice(2));
      if (Number.isInteger(maybeCardId) && maybeCardId > 0) {
        return { kind: 'card', cardId: maybeCardId };
      }
      return null;
    }

    if (lower.startsWith('uc-')) {
      const rest = trimmed.slice(3);
      const firstDash = rest.indexOf('-');
      if (firstDash > 0) {
        const userIdStr = rest.slice(0, firstDash);
        const chatStr = rest.slice(firstDash + 1).trim();
        const maybeUserId = Number(userIdStr);
        if (!Number.isNaN(maybeUserId) && chatStr.length > 0) {
          return {
            kind: 'userChat',
            userId: maybeUserId,
            chatId: chatStr
          };
        }
      }
      return null;
    }

    if (lower.startsWith('u-')) {
      const userIdStr = trimmed.slice(2);
      const maybeUserId = Number(userIdStr);
      if (!Number.isNaN(maybeUserId)) {
        return { kind: 'user', userId: maybeUserId };
      }
      return null;
    }

    if (lower.startsWith('casino-')) {
      const chatStr = trimmed.slice(7).trim(); // Remove 'casino-'
      if (chatStr.length > 0) {
        return {
          kind: 'casino',
          chatId: chatStr
        };
      }
      return null;
    }

    return null;
  }

  static initializeUser(): UserData | null {
    try {
      // Check if WebApp is properly initialized
      if (!WebApp || !WebApp.initDataUnsafe) {
        throw new Error("Telegram Web App not properly initialized. Please open this app from Telegram.");
      }

      // Check if user data is available
      if (!WebApp.initDataUnsafe.user) {
        throw new Error("User data not available. Please make sure you're logged into Telegram.");
      }

      const currentUserId = WebApp.initDataUnsafe.user.id;
      if (typeof currentUserId !== 'number') {
        throw new Error("Could not determine your Telegram user id.");
      }

      let targetUserId: number = currentUserId;
      let chatId: string | null = null;
      let singleCardId: number | null = null;

      let payloadType: 'card' | 'user' | 'userChat' | 'casino' | null = null;
      let payloadSource: string | null = null;

      const applyExternalPayload = (rawValue: string, source: string): boolean => {
        if (!rawValue) {
          return false;
        }

        let decoded = rawValue;
        try {
          decoded = decodeURIComponent(rawValue);
        } catch (decodeErr) {
          console.error(`Error decoding ${source}:`, decodeErr);
        }

        const decodedToken = TelegramUtils.decodeToken(decoded);
        const tokenPayload = decodedToken ?? decoded;

        const parsed = TelegramUtils.parsePayload(tokenPayload);
        if (!parsed) {
          console.warn('Unrecognized token payload ignored', { source, tokenPayload });
          return false;
        }

        switch (parsed.kind) {
          case 'card':
            singleCardId = parsed.cardId;
            payloadType = 'card';
            payloadSource = source;
            return true;
          case 'user':
            targetUserId = parsed.userId;
            singleCardId = null;
            payloadType = 'user';
            payloadSource = source;
            return true;
          case 'userChat':
            targetUserId = parsed.userId;
            chatId = parsed.chatId;
            singleCardId = null;
            payloadType = 'userChat';
            payloadSource = source;
            return true;
          case 'casino':
            chatId = parsed.chatId;
            singleCardId = null;
            payloadType = 'casino';
            payloadSource = source;
            return true;
          default:
            return false;
        }
      };

      const startParamRaw = WebApp.initDataUnsafe.start_param;
      const startParam = startParamRaw ?? null;
      if (startParam) {
        applyExternalPayload(startParam, 'init data start_param');
      }

      if (payloadType && payloadSource) {
        switch (payloadType) {
          case 'card':
            console.info('Start parameter requested single card view', {
              source: payloadSource
            });
            break;
          case 'user':
            console.info('Start parameter requested user collection', {
              source: payloadSource
            });
            break;
          case 'userChat':
            console.info('Start parameter requested user collection scoped to chat', {
              source: payloadSource
            });
            break;
          case 'casino':
            console.info('Start parameter requested casino catalog', {
              source: payloadSource
            });
            break;
        }
      } else {
        console.info('No start parameter supplied; defaulting to init data user context', {
          source: 'initDataUnsafe.user'
        });
      }

      const casinoView = payloadType === 'casino';
      const isOwnCollection = singleCardId == null && targetUserId === currentUserId; // In single card mode collection semantics disabled
      const enableTrade = isOwnCollection && singleCardId == null;

      return {
        currentUserId,
        targetUserId,
        isOwnCollection,
        enableTrade,
        chatId,
        singleCardId,
        singleCardView: singleCardId != null,
        casinoView,
        collectionDisplayName: null,
        collectionUsername: null,
      };
    } catch (err) {
      console.error('Error initializing user:', err);
      return null;
    }
  }

  static getInitData(): string | null {
    // Get the raw init data from Telegram WebApp
    try {
      if (!WebApp || !WebApp.initData) {
        return null;
      }
      return WebApp.initData;
    } catch (err) {
      console.error('Error getting init data:', err);
      return null;
    }
  }

  static getCurrentUsername(): string | null {
    try {
      if (!WebApp || !WebApp.initDataUnsafe || !WebApp.initDataUnsafe.user) {
        return null;
      }
      return WebApp.initDataUnsafe.user.username || null;
    } catch (err) {
      console.error('Error getting current username:', err);
      return null;
    }
  }

  static setupBackButton(clickHandler: () => void) {
    if (!WebApp.BackButton) {
      return () => { };
    }

    WebApp.BackButton.onClick(clickHandler);
    WebApp.BackButton.show();

    return () => {
      WebApp.BackButton.offClick(clickHandler);
      WebApp.BackButton.hide();
    };
  }

  static hideBackButton() {
    if (!WebApp.BackButton) {
      return;
    }

    WebApp.BackButton.hide();
  }

  static showAlert(message: string) {
    if (WebApp && WebApp.showAlert) {
      WebApp.showAlert(message);
    } else {
      alert(message);
    }
  }

  static closeApp() {
    if (WebApp && WebApp.close) {
      WebApp.close();
    }
  }

  static expandApp() {
    if (WebApp && WebApp.expand) {
      WebApp.expand();
    }
  }

  static isExpanded(): boolean {
    return WebApp && WebApp.isExpanded ? WebApp.isExpanded : false;
  }

  static getViewportStableHeight(): number | null {
    return WebApp && WebApp.viewportStableHeight ? WebApp.viewportStableHeight : null;
  }

  static onViewportChanged(callback: (event: { isStateStable: boolean }) => void) {
    if (!WebApp || !WebApp.onEvent) return () => { };

    const handler = (event: { isStateStable: boolean }) => {
      callback(event);
    };

    WebApp.onEvent('viewportChanged', handler);

    return () => {
      if (WebApp.offEvent) {
        WebApp.offEvent('viewportChanged', handler);
      }
    };
  }

  static startOrientationTracking(callback: (data: OrientationData) => void) {
    if (!WebApp.DeviceOrientation) return () => { };

    let intervalId: ReturnType<typeof setInterval> | null = null;

    const updateOrientation = () => {
      callback({
        alpha: WebApp.DeviceOrientation.alpha || 0,
        beta: WebApp.DeviceOrientation.beta || 0,
        gamma: WebApp.DeviceOrientation.gamma || 0,
        isStarted: WebApp.DeviceOrientation.isStarted || false
      });
    };

    // Start tracking with 100ms refresh rate for smooth animations
    WebApp.DeviceOrientation.start({
      refresh_rate: 100,
      need_absolute: false
    }, (started) => {
      if (started) {
        updateOrientation();
        // Start polling for orientation updates
        intervalId = setInterval(updateOrientation, 100);
      }
    });

    // Initial update
    updateOrientation();

    return () => {
      if (intervalId) {
        clearInterval(intervalId);
      }
      WebApp.DeviceOrientation.stop();
    };
  }

  // Haptic Feedback Methods
  static triggerHapticImpact(style: 'light' | 'medium' | 'heavy' = 'medium') {
    try {
      if (WebApp.HapticFeedback && WebApp.HapticFeedback.impactOccurred) {
        WebApp.HapticFeedback.impactOccurred(style);
      }
    } catch (err) {
      console.warn('Haptic feedback not available or failed:', err);
    }
  }

  static triggerHapticNotification(type: 'success' | 'warning' | 'error' = 'success') {
    try {
      if (WebApp.HapticFeedback && WebApp.HapticFeedback.notificationOccurred) {
        WebApp.HapticFeedback.notificationOccurred(type);
      }
    } catch (err) {
      console.warn('Haptic feedback not available or failed:', err);
    }
  }

  static triggerHapticSelection() {
    try {
      if (WebApp.HapticFeedback && WebApp.HapticFeedback.selectionChanged) {
        WebApp.HapticFeedback.selectionChanged();
      }
    } catch (err) {
      console.warn('Haptic feedback not available or failed:', err);
    }
  }
}