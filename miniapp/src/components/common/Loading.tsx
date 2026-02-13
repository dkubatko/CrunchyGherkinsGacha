import React, { useMemo } from 'react';
import './Loading.css';

interface LoadingProps {
  /** Optional message to display below the spinner */
  message?: string;
}

const SPINNER_DURATION_MS = 900;

const getContinuousSpinnerDelay = (): string => {
  const now = typeof performance !== 'undefined' ? performance.now() : Date.now();
  const offsetMs = now % SPINNER_DURATION_MS;
  return `-${(offsetMs / 1000).toFixed(4)}s`;
};

const Loading: React.FC<LoadingProps> = ({ message = 'Loading...' }) => {
  const animationDelay = useMemo(() => getContinuousSpinnerDelay(), []);

  return (
    <div className="loading-fullscreen">
      <div
        className="loading-spinner"
        style={{ '--loading-spin-delay': animationDelay } as React.CSSProperties}
      />
      <p className="loading-message">{message}</p>
    </div>
  );
};

export default Loading;
