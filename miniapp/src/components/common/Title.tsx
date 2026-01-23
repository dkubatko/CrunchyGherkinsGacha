import React from 'react';
import './Title.css';

// SpinsBadge sub-component for displaying spin count with animated coin
export interface SpinsBadgeProps {
  count: number;
}

export const SpinsBadge: React.FC<SpinsBadgeProps> = ({ count }) => (
  <div className="title-spins-badge">
    <span className="title-spins-coin" aria-hidden="true" />
    <span className="title-spins-count">{count}</span>
  </div>
);

// PositionIndicator sub-component for displaying card position (e.g., "5 / 20")
export interface PositionIndicatorProps {
  current: number | string;
  total: number | string;
}

export const PositionIndicator: React.FC<PositionIndicatorProps> = ({ current, total }) => (
  <div className="title-position-indicator">
    <span className="title-position-current">{current}</span>
    <span className="title-position-separator"> / </span>
    <span className="title-position-total">{total}</span>
  </div>
);

// ViewToggleButton sub-component for switching between grid/gallery views
export interface ViewToggleButtonProps {
  isGridView: boolean;
  onClick: () => void;
  disabled?: boolean;
}

export const ViewToggleButton: React.FC<ViewToggleButtonProps> = ({ isGridView, onClick, disabled }) => (
  <button
    className="title-view-toggle"
    onClick={onClick}
    onTouchStart={(e) => e.stopPropagation()}
    onTouchEnd={(e) => e.stopPropagation()}
    disabled={disabled}
    aria-label={isGridView ? 'Currently in grid view' : 'Currently in gallery view'}
  >
    {isGridView ? 'Grid' : 'Gallery'}
  </button>
);

// Main Title component props
export interface TitleProps {
  /** The title text to display */
  title: string;
  /** Optional content to render on the left side (e.g., position indicator) */
  leftContent?: React.ReactNode;
  /** Optional content to render on the right side (badges, buttons, etc.) */
  rightContent?: React.ReactNode;
  /** When true, shows a loading state */
  loading?: boolean;
  /** When true, renders with fullscreen backdrop (for loading screens) */
  fullscreen?: boolean;
}

const Title: React.FC<TitleProps> = ({ title, leftContent, rightContent, loading, fullscreen }) => {
  const content = (
    <div className="title-container">
      <div className="title-left-content">
        {leftContent}
      </div>
      <h1 className="title-text">{title}</h1>
      <div className="title-right-content">
        {rightContent}
        {loading && !rightContent && <div className="title-loading-indicator" />}
      </div>
    </div>
  );

  if (fullscreen) {
    return <div className="title-fullscreen-backdrop">{content}</div>;
  }

  return content;
};

export default Title;
