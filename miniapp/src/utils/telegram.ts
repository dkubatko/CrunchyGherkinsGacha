import WebApp from '@twa-dev/sdk';
import type { UserData, OrientationData } from '../types';

export class TelegramUtils {
  private static readonly TOKEN_PREFIX = 'tg1_';

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

      const applyExternalPayload = (value: string, source: string) => {
        if (!value) {
          return;
        }

        let decoded = value;
        try {
          decoded = decodeURIComponent(value);
        } catch (decodeErr) {
          console.error(`Error decoding ${source}:`, decodeErr);
        }

        const decodedToken = TelegramUtils.decodeToken(decoded);
        const tokenPayload = decodedToken ?? decoded;

        // Parse the simple token format: user_id or user_id.chat_id
        const trimmed = tokenPayload.trim();
        if (!trimmed) {
          return;
        }

        // Check if it's the simple token format (numbers and dots only)
        if (/^[\d.-]+$/.test(trimmed)) {
          const parts = trimmed.split('.');
          const userIdStr = parts[0];
          const chatIdStr = parts[1]; // Optional chat_id

          const maybeUserId = Number(userIdStr);
          if (!Number.isNaN(maybeUserId)) {
            targetUserId = maybeUserId;
          }

          if (chatIdStr) {
            chatId = chatIdStr;
          }
          return;
        }

        // Fallback: try to parse as a simple number
        const maybeNumber = Number(trimmed);
        if (!Number.isNaN(maybeNumber)) {
          targetUserId = maybeNumber;
        }
      };

      const payloadCandidates: (string | null)[] = [
        WebApp.initDataUnsafe.start_param ?? null,
      ];

      const urlParams = new URLSearchParams(window.location.search);
      payloadCandidates.push(urlParams.get('startapp'));
      payloadCandidates.push(urlParams.get('v'));

      for (const candidate of payloadCandidates) {
        if (candidate) {
          applyExternalPayload(candidate, 'mini app payload');
          break;
        }
      }

      const isOwnCollection = targetUserId === currentUserId;
      const enableTrade = isOwnCollection;

      return {
        currentUserId,
        targetUserId,
        isOwnCollection,
        enableTrade,
        chatId,
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

  static setupMainButton(buttonText: string, clickHandler: () => void) {
    WebApp.MainButton.setText(buttonText);
    WebApp.MainButton.show();
    WebApp.MainButton.onClick(clickHandler);

    return () => {
      WebApp.MainButton.hide();
      WebApp.MainButton.offClick(clickHandler);
    };
  }

  static hideMainButton() {
    WebApp.MainButton.hide();
    return () => { };
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

  static startOrientationTracking(callback: (data: OrientationData) => void) {
    if (!WebApp.DeviceOrientation) return () => { };

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
        const interval = setInterval(updateOrientation, 100);
        return () => clearInterval(interval);
      }
    });

    // Initial update
    updateOrientation();

    return () => {
      WebApp.DeviceOrientation.stop();
    };
  }
}