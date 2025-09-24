import { useState, useEffect } from 'react';
import { useSwipeable } from 'react-swipeable';
import WebApp from '@twa-dev/sdk';
import './App.css';
import Card from './components/Card';

interface CardData {
  id: number;
  base_name: string;
  modifier: string;
  rarity: string;
  image_b64: string;
}

interface OrientationData {
  alpha: number;
  beta: number;
  gamma: number;
  isStarted: boolean;
}

function App() {
  const [cards, setCards] = useState<CardData[]>([]);
  const [currentIndex, setCurrentIndex] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [collectionUsername, setCollectionUsername] = useState<string>('');
  const [isOwnCollection, setIsOwnCollection] = useState(false);
  const [orientation, setOrientation] = useState<OrientationData>({
    alpha: 0,
    beta: 0,
    gamma: 0,
    isStarted: false
  });
  const [orientationKey, setOrientationKey] = useState(0);

  // Initialize user data and collection info
  useEffect(() => {
    const initializeApp = () => {
      try {
        // Check if WebApp is properly initialized
        if (!WebApp || !WebApp.initDataUnsafe) {
          setError("Telegram Web App not properly initialized. Please open this app from Telegram.");
          return null;
        }

        // Check if user data is available
        if (!WebApp.initDataUnsafe.user) {
          setError("User data not available. Please make sure you're logged into Telegram.");
          return null;
        }

        // Get the current user's username from Telegram
        const currentUserUsername = WebApp.initDataUnsafe.user.username;
        if (!currentUserUsername || currentUserUsername.trim() === '') {
          setError("Could not determine your username. Please make sure you have a username set in your Telegram profile.");
          return null;
        }

        // Get the collection username from URL parameters
        const urlParams = new URLSearchParams(window.location.search);
        let fetchUsername = urlParams.get('v') || currentUserUsername;
        
        // Remove any URL encoding artifacts
        fetchUsername = decodeURIComponent(fetchUsername);
        setCollectionUsername(fetchUsername);
        
        // Check if this is the user's own collection
        const isOwn = currentUserUsername === fetchUsername;
        setIsOwnCollection(isOwn);

        return fetchUsername;
      } catch (err) {
        if (err instanceof Error) {
          setError(err.message);
        } else {
          setError('An error occurred during app initialization');
        }
        return null;
      }
    };

    const fetchCards = async (username: string) => {
      try {
        const apiBaseUrl = import.meta.env.VITE_API_BASE_URL || 'https://api.crunchygherkins.com';
        
        // Build the request URL
        const requestUrl = `${apiBaseUrl}/cards/${username}`;
        
        // Prepare headers with authentication token from URL query parameter
        const headers: HeadersInit = {
          'Content-Type': 'application/json',
        };
        
        // Get token from URL query parameters
        const urlParams = new URLSearchParams(window.location.search);
        const authToken = urlParams.get('token');
        console.log('Auth token from URL:', authToken);
        if (authToken) {
          headers['Authorization'] = `Bearer ${authToken}`;
        }
        
        const response = await fetch(requestUrl, { headers });
        if (!response.ok) {
          if (response.status === 404) {
            throw new Error('User not found. They may not have any cards yet.');
          } else if (response.status === 401) {
            throw new Error('Authentication failed. Please reopen the app from Telegram.');
          } else if (response.status >= 500) {
            throw new Error('Server error. Please try again later.');
          } else {
            throw new Error(`Failed to fetch cards (Error ${response.status})`);
          }
        }
        const data = await response.json();
        setCards(data);
      } catch (err) {
        if (err instanceof Error) {
          setError(err.message);
        } else {
          setError('An unknown error occurred while fetching cards');
        }
      } finally {
        setLoading(false);
      }
    };

    const username = initializeApp();
    if (username) {
      // Only fetch cards if initialization was successful
      fetchCards(username);
    } else {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    // Start device orientation tracking
    if (WebApp.DeviceOrientation) {
      const updateOrientation = () => {
        setOrientation({
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
          // Set up periodic updates
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
  }, []);

  // Handle MainButton for trading
  useEffect(() => {
    if (!loading && !error && isOwnCollection && cards.length > 0) {
      // Show the Trade button only if viewing own collection
      WebApp.MainButton.setText("Trade");
      WebApp.MainButton.show();
      
      const handleTradeClick = () => {
        // Here you can implement the trade functionality
        // For now, just show an alert or implement your trade logic
        WebApp.showAlert("Trade functionality coming soon!");
      };
      
      WebApp.MainButton.onClick(handleTradeClick);
      
      return () => {
        WebApp.MainButton.hide();
        WebApp.MainButton.offClick(handleTradeClick);
      };
    } else {
      // Hide the button if not own collection or no cards
      WebApp.MainButton.hide();
    }
  }, [loading, error, isOwnCollection, cards.length]);

  // Reset tilt reference by incrementing key
  const resetTiltReference = () => {
    setOrientationKey(prev => prev + 1);
  };

  const handlers = useSwipeable({
    onSwipedLeft: () => {
      setCurrentIndex((prevIndex) => {
        const newIndex = (prevIndex + 1) % cards.length; // Wrap to 0 after last card
        resetTiltReference();
        return newIndex;
      });
    },
    onSwipedRight: () => {
      setCurrentIndex((prevIndex) => {
        const newIndex = prevIndex === 0 ? cards.length - 1 : prevIndex - 1; // Wrap to last card from first
        resetTiltReference();
        return newIndex;
      });
    },
    preventScrollOnSwipe: true,
    trackMouse: true
  });

  if (loading) {
    return <div className="app-container"><h1>Loading cards...</h1></div>;
  }

  if (error) {
    return <div className="app-container"><h1>Error: {error}</h1></div>;
  }

  return (
    <div className="app-container" {...handlers}>
      <h1 style={{ marginBottom: '2vh' }}>@{collectionUsername}'s collection</h1>
      
      {cards.length > 0 ? (
        <div className="card-container">
          <div className="navigation-dots" style={{ marginBottom: '2vh' }}>
            {cards.map((_, index) => (
              <span
                key={index}
                className={`dot ${currentIndex === index ? 'active' : ''}`}
                onClick={() => {
                  if (index !== currentIndex) {
                    setCurrentIndex(index);
                    resetTiltReference();
                  }
                }}
              ></span>
            ))}
          </div>
          <Card 
            {...cards[currentIndex]} 
            orientation={orientation}
            tiltKey={orientationKey}
          />
        </div>
      ) : (
        <p>{isOwnCollection ? "You don't own any cards yet." : `@${collectionUsername} doesn't own any cards yet.`}</p>
      )}
    </div>
  );
}

export default App;
