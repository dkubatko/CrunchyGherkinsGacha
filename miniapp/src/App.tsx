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
  const [username, setUsername] = useState<string>('');
  const [orientation, setOrientation] = useState<OrientationData>({
    alpha: 0,
    beta: 0,
    gamma: 0,
    isStarted: false
  });
  const [orientationKey, setOrientationKey] = useState(0);

  useEffect(() => {
    const fetchCards = async () => {
      try {
        // Check if WebApp is properly initialized
        if (!WebApp || !WebApp.initDataUnsafe) {
          setError("Telegram Web App not properly initialized. Please open this app from Telegram.");
          setLoading(false);
          return;
        }

        // Check if user data is available
        if (!WebApp.initDataUnsafe.user) {
          setError("User data not available. Please make sure you're logged into Telegram.");
          setLoading(false);
          return;
        }

        // Get the username from start parameter or fall back to Telegram Web App user object
        let fetchedUsername: string | undefined;
        
        // First, check if there's a start parameter with a username
        if (WebApp.initDataUnsafe.start_param) {
          fetchedUsername = WebApp.initDataUnsafe.start_param;
        } else {
          // Fall back to the user's Telegram username
          fetchedUsername = WebApp.initDataUnsafe.user.username;
        }
        
        // Check if username exists and is not empty
        if (!fetchedUsername || fetchedUsername.trim() === '') {
          setError("Could not determine username. Please make sure you have a username set in your Telegram profile or the app was opened with a valid start parameter.");
          setLoading(false);
          return;
        }

        setUsername(fetchedUsername);

        const apiBaseUrl = import.meta.env.VITE_API_BASE_URL || 'https://api.crunchygherkins.com';
        const response = await fetch(`${apiBaseUrl}/cards/${fetchedUsername}`);
        if (!response.ok) {
          if (response.status === 404) {
            throw new Error('User not found. You may not have any cards yet.');
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
          setError('An unknown error occurred while fetching your cards');
        }
      } finally {
        setLoading(false);
      }
    };

    fetchCards();
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
      <h1 style={{ marginBottom: '2vh' }}>@{username}'s collection</h1>
      
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
        <p>You don't own any cards yet.</p>
      )}
    </div>
  );
}

export default App;
