import React, { useState, useEffect } from 'react';
import logo from '@/assets/splash/logo_splash.webp';
import './SplashScreen.css';

interface SplashScreenProps {
  progress: number;
  ready: boolean;
  onTransitionEnd: () => void;
}

const SplashScreen: React.FC<SplashScreenProps> = ({ progress, ready, onTransitionEnd }) => {
  const [fadeOut, setFadeOut] = useState(false);

  useEffect(() => {
    if (ready) {
      // Small delay to ensure progress bar reaches 100% visually
      const timer = setTimeout(() => setFadeOut(true), 150);
      return () => clearTimeout(timer);
    }
  }, [ready]);

  const handleAnimationEnd = (e: React.AnimationEvent) => {
    if (e.animationName === 'splashFadeOut') {
      onTransitionEnd();
    }
  };

  // Progress as decimal for scaleX transform
  const progressScale = Math.min(progress, 1);

  return (
    <div
      className={`splash-screen ${fadeOut ? 'splash-fade-out' : ''}`}
      onAnimationEnd={handleAnimationEnd}
    >
      <div className="splash-content">
        <img src={logo} alt="Crunchy Gherkins" className="splash-logo" />
        <h1 className="splash-title">Crunchy Gherkins</h1>

        <div className="splash-progress-container">
          <div className="splash-progress-track">
            <div 
              className="splash-progress-fill" 
              style={{ transform: `scaleX(${progressScale})` }}
            />
          </div>
        </div>
      </div>
    </div>
  );
};

export default SplashScreen;
