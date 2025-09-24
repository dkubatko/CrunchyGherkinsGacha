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

      // Get the current user's username from Telegram
      const currentUserUsername = WebApp.initDataUnsafe.user.username;
      if (!currentUserUsername || currentUserUsername.trim() === '') {
        throw new Error("Could not determine your username. Please make sure you have a username set in your Telegram profile.");
      }

      // Get the collection username from URL parameters
      const urlParams = new URLSearchParams(window.location.search);
      let fetchUsername = urlParams.get('v') || currentUserUsername;
      
      // Remove any URL encoding artifacts
      fetchUsername = decodeURIComponent(fetchUsername);
      
      // Check if this is the user's own collection
      const isOwnCollection = currentUserUsername === fetchUsername;

      return {
        username: fetchUsername,
        isOwnCollection
      };
    } catch (err) {
      console.error('Error initializing user:', err);
      return null;
    }
  }

  static getAuthToken(): string | null {
    const urlParams = new URLSearchParams(window.location.search);
    return urlParams.get('token');
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
    return () => {};
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
    if (!WebApp.DeviceOrientation) return () => {};

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