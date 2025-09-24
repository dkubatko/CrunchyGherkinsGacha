import WebApp from '@twa-dev/sdk';
import type { UserData, OrientationData } from '../types';

export class TelegramUtils {
  private static parseStartParam(): { view?: string; token?: string } | null {
    try {
      if (!WebApp?.initDataUnsafe?.start_param) {
        console.log('No start_param found in WebApp initData');
        return null;
      }

      const startParam = WebApp.initDataUnsafe.start_param;
      console.log('Found start_param:', startParam);

      // Base64 decode the start_param
      // Add padding if necessary
      const padded = startParam + '='.repeat((4 - startParam.length % 4) % 4);
      const decoded = atob(padded.replace(/-/g, '+').replace(/_/g, '/'));
      const parsedData = JSON.parse(decoded);
      
      console.log('Parsed start_param data:', parsedData);
      return parsedData;
    } catch (err) {
      console.error('Error parsing start_param:', err);
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

      // Get the current user's username from Telegram
      const currentUserUsername = WebApp.initDataUnsafe.user.username;
      if (!currentUserUsername || currentUserUsername.trim() === '') {
        throw new Error("Could not determine your username. Please make sure you have a username set in your Telegram profile.");
      }

      let fetchUsername = currentUserUsername;
      let dataSource = 'default';

      // Try to get data from start_param first (production mode)
      const startParamData = this.parseStartParam();
      if (startParamData?.view) {
        fetchUsername = startParamData.view;
        dataSource = 'start_param';
        console.log('Using view username from start_param (production mode)');
      } else {
        // Fallback to URL parameters (debug mode)
        console.log('No start_param data, checking URL parameters (debug mode)');
        const urlParams = new URLSearchParams(window.location.search);
        const urlView = urlParams.get('v');
        if (urlView) {
          fetchUsername = urlView;
          dataSource = 'url_params';
          console.log('Using view username from URL parameters');
        }
      }
      
      // Remove any URL encoding artifacts
      fetchUsername = decodeURIComponent(fetchUsername);
      
      // Check if this is the user's own collection
      const isOwnCollection = currentUserUsername === fetchUsername;

      console.log('User initialized:', { 
        currentUserUsername, 
        fetchUsername, 
        isOwnCollection,
        dataSource
      });

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
    let token = null;
    let tokenSource = 'none';

    // Try to get token from start_param first (production mode)
    const startParamData = this.parseStartParam();
    if (startParamData?.token) {
      token = startParamData.token;
      tokenSource = 'start_param';
      console.log('Using token from start_param (production mode)');
    } else {
      // Fallback to URL parameters (debug mode)
      console.log('No start_param token, checking URL parameters (debug mode)');
      const urlParams = new URLSearchParams(window.location.search);
      token = urlParams.get('token');
      
      if (token) {
        tokenSource = 'url_params';
        console.log('Using token from URL parameters');
      } else {
        console.log('No token found in either start_param or URL parameters');
      }
    }
    
    console.log('Token resolution:', { found: !!token, source: tokenSource });
    return token;
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