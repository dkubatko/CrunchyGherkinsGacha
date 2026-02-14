import React from 'react';
import BeatLoader from 'react-spinners/BeatLoader';
import './Loading.css';

interface LoadingProps {
  /** Optional message to display below the spinner */
  message?: string;
}

const Loading: React.FC<LoadingProps> = ({ message = 'Loading...' }) => {
  return (
    <div className="loading-fullscreen">
      <BeatLoader
        color="var(--tg-theme-button-color, #007aff)"
        size={10}
        speedMultiplier={0.5}
      />
      <p className="loading-message">{message}</p>
    </div>
  );
};

export default Loading;
