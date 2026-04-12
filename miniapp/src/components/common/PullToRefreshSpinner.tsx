import React from 'react';
import './PullToRefreshSpinner.css';

const SPINNER_SIZE = 24;
const THRESHOLD = 64;

interface PullToRefreshSpinnerProps {
  pullDistance: number;
  spinnerAngle: number;
  isRefreshing: boolean;
}

const PullToRefreshSpinner: React.FC<PullToRefreshSpinnerProps> = ({
  pullDistance,
  spinnerAngle,
  isRefreshing,
}) => {
  if (pullDistance <= 0 && !isRefreshing) return null;

  const showIcon = pullDistance >= SPINNER_SIZE;
  // Full opacity during refresh; fade in from SPINNER_SIZE to THRESHOLD during drag
  const opacity = isRefreshing
    ? 1
    : showIcon
      ? Math.min((pullDistance - SPINNER_SIZE) / (THRESHOLD - SPINNER_SIZE), 1)
      : 0;

  return (
    <div
      className="ptr-spinner-container"
      style={{ height: pullDistance }}
    >
      {showIcon && (
        <svg
          className="ptr-spinner-icon"
          width={SPINNER_SIZE}
          height={SPINNER_SIZE}
          viewBox="0 0 24 24"
          fill="none"
          style={{
            transform: `rotate(${spinnerAngle}deg)`,
            opacity,
          }}
        >
          {/* Static background track */}
          <circle
            cx="12"
            cy="12"
            r="9"
            stroke="rgba(255, 255, 255, 0.15)"
            strokeWidth="2.5"
            fill="none"
          />
          {/* Rotating arc segment */}
          <circle
            cx="12"
            cy="12"
            r="9"
            stroke="rgba(255, 255, 255, 0.7)"
            strokeWidth="2.5"
            fill="none"
            strokeLinecap="round"
            strokeDasharray="28 28"
          />
        </svg>
      )}
    </div>
  );
};

export default PullToRefreshSpinner;
