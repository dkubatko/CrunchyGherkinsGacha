import WebApp from '@twa-dev/sdk';
import type { UserData, OrientationData } from '../types';

export class TelegramUtils {
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

        try {
          const parsed = JSON.parse(decoded);
          if (parsed && typeof parsed === 'object') {
            const parsedUserIdRaw = parsed.user_id ?? parsed.target_user_id ?? parsed.userId;
            const parsedChatId = parsed.chat_id ?? parsed.chatId;

            if (parsedUserIdRaw !== undefined && parsedUserIdRaw !== null) {
              const maybeNumber = typeof parsedUserIdRaw === 'number'
                ? parsedUserIdRaw
                : Number(String(parsedUserIdRaw));
              if (!Number.isNaN(maybeNumber)) {
                targetUserId = maybeNumber;
              }
            }

            if (typeof parsedChatId === 'string') {
              chatId = parsedChatId.trim() || null;
            }

            return;
          }
        } catch (parseErr) {
          console.error(`Error parsing ${source}:`, parseErr);
        }

        const trimmed = decoded.trim();
        if (!trimmed) {
          return;
        }

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