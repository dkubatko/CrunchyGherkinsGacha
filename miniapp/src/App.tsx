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
        // In a real app, you'd get the username from the Telegram Web App user object
        const fetchedUsername = WebApp.initDataUnsafe?.user?.username || "Your";
        setUsername(fetchedUsername);
        
        if (!fetchedUsername) {
          setError("Could not determine Telegram username.");
          setLoading(false);
          return;
        }

        const response = await fetch(`https://api.crunchygherkins.com/cards/${fetchedUsername}`);
        if (!response.ok) {
          throw new Error('Failed to fetch cards');
        }
        const data = await response.json();
        setCards(data);
      } catch (err) {
        setError(err instanceof Error ? err.message : 'An unknown error occurred');
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
