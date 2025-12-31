/**
 * RTBCard - Motion-enabled card component for RideTheBus
 * 
 * Handles layout animations (arc ↔ stack transitions) and flip reveal animations
 * using Framer Motion's layoutId for shared element transitions.
 * 
 * Flip Animation Structure:
 * - Outer motion.div: handles layout position (x, y, rotate via variants)
 * - Inner motion.div: handles 3D flip rotation (rotateY)
 * - Two face divs: front (image) and back (placeholder) with backface-visibility: hidden
 */

import React, { useRef, useEffect } from 'react';
import { motion } from 'framer-motion';
import {
  cardLayoutVariants,
  cardFlipVariants,
  getArcPosition,
  getLeftStackPosition,
  getRightStackPosition,
  getLeftStackAbsolutePosition,
  getRightStackAbsolutePosition,
} from '../utils/rtbAnimations';
import type { RTBCardInfo } from '../types';

// =============================================================================
// TYPES
// =============================================================================

export type CardLayoutVariant = 'hidden' | 'arc' | 'arcSelected' | 'stackLeft' | 'stackRight' | 'exit';

export interface RTBCardProps {
  /** Card data from the API */
  card: RTBCardInfo;
  
  /** Unique identifier for layout animations */
  cardId: number | string;
  
  /** Current layout variant */
  variant: CardLayoutVariant;
  
  /** Initial variant for animation start position (defaults to 'hidden') */
  initialVariant?: CardLayoutVariant;
  
  /** Position index within the current layout */
  index: number;
  
  /** Total cards in the current layout group */
  total: number;
  
  /** Initial index for animation start position */
  initialIndex?: number;
  
  /** Initial total for animation start position */
  initialTotal?: number;
  
  /** Whether this card is revealed (showing image vs placeholder) */
  isRevealed: boolean;
  
  /** Whether this card is currently selected (finished phase) */
  isSelected?: boolean;
  
  /** Whether this is the losing card (red glow) */
  isLosing?: boolean;
  
  /** Whether this is the top card in a stack (blue glow) */
  isTop?: boolean;
  
  /** Whether the card is currently flipping (triggers flip animation) */
  isFlipping?: boolean;
  
  /** 
   * Use absolute position calculations (relative to .rtb-main-cards center)
   * instead of relative positions (within stack container).
   * Set to true for cards animating BETWEEN stacks.
   */
  useAbsolutePosition?: boolean;
  
  /** z-index for stacking order */
  zIndex?: number;
  
  /**
   * Skip the initial animation (opacity/scale fade-in).
   * Set to true for cards that already existed and are just repositioning,
   * to prevent the "pop-in" effect when cards move between stacks.
   */
  skipInitialAnimation?: boolean;
  
  /** Click handler */
  onClick?: (e?: React.MouseEvent) => void;
  
  /** Called when flip animation completes */
  onFlipComplete?: () => void;
  
  /** Called when layout animation completes */
  onLayoutAnimationComplete?: () => void;
}

// =============================================================================
// COMPONENT
// =============================================================================

const RTBCard: React.FC<RTBCardProps> = ({
  card,
  cardId,
  variant,
  initialVariant,
  index,
  total,
  initialIndex,
  initialTotal,
  isRevealed,
  isSelected = false,
  isLosing = false,
  isTop = false,
  isFlipping = false,
  useAbsolutePosition = false,
  zIndex = 1,
  skipInitialAnimation = false,
  onClick,
  onFlipComplete,
  onLayoutAnimationComplete,
}) => {
  // Track if flip animation has been triggered to ensure callback fires only once
  const flipStartedRef = useRef(false);
  const layoutCallbackFiredRef = useRef(false);
  
  // Reset refs when isFlipping changes
  useEffect(() => {
    if (isFlipping) {
      flipStartedRef.current = true;
    }
  }, [isFlipping]);
  
  // Determine layout class based on variant
  const isArcLayout = variant === 'arc' || variant === 'arcSelected';
  const isStackLayout = variant === 'stackLeft' || variant === 'stackRight';
  
  // Determine the actual animation variant to use
  // If in arc layout and selected, use arcSelected variant
  const animationVariant = (variant === 'arc' && isSelected) ? 'arcSelected' : variant;
  
  // Determine flip state:
  // - If flipping, animate to faceUp (will show front face mid-flip)
  // - If revealed, show faceUp
  // - Otherwise show faceDown
  const flipVariant = isFlipping || isRevealed ? 'faceUp' : 'faceDown';
  
  // Build class names for styling
  const cardClasses = [
    'rtb-card',
    isRevealed ? 'revealed' : 'hidden',
    isArcLayout && 'rtb-card-arc',
    isStackLayout && 'rtb-card-stacked',
    isSelected && 'rtb-card-selected',
    isLosing && 'rtb-card-losing',
    isTop && 'rtb-card-top',
  ].filter(Boolean).join(' ');

  // Compute initial position for layout animation
  const initVariant = initialVariant || 'hidden';
  const initIndex = initialIndex ?? index;
  const initTotal = initialTotal ?? total;
  
  // Compute explicit initial position for layout animation
  // Returns false to skip initial animation (Framer Motion's initial={false})
  const getInitialPosition = (): false | { opacity?: number; scale?: number; y?: number; x?: number; rotate?: number } => {
    // Skip initial animation for cards that already existed
    // This prevents the "pop-in" effect when cards just reposition
    if (skipInitialAnimation) {
      return false;
    }
    if (initVariant === 'hidden') {
      return { opacity: 0, scale: 0.8, y: 20 };
    }
    if (initVariant === 'stackRight') {
      const pos = useAbsolutePosition 
        ? getRightStackAbsolutePosition(initIndex)
        : getRightStackPosition(initIndex);
      return { x: pos.x, y: pos.y, rotate: pos.rotate, scale: 1, opacity: 1 };
    }
    if (initVariant === 'stackLeft') {
      const pos = useAbsolutePosition
        ? getLeftStackAbsolutePosition(initIndex, initTotal)
        : getLeftStackPosition(initIndex, initTotal);
      return { x: pos.x, y: pos.y, rotate: pos.rotate, scale: 1, opacity: 1 };
    }
    if (initVariant === 'arc' || initVariant === 'arcSelected') {
      const pos = getArcPosition(initIndex, initTotal);
      return { x: pos.x, y: pos.y, rotate: pos.rotate, scale: 1, opacity: 1 };
    }
    // For unrecognized variants, skip initial animation and let animate take over
    return false;
  };
  
  // Compute explicit target position for layout animation (when using absolute positions)
  const getTargetPosition = () => {
    if (!useAbsolutePosition) {
      return undefined; // Use variant-based animation
    }
    if (animationVariant === 'stackLeft') {
      const pos = getLeftStackAbsolutePosition(index, total);
      return { x: pos.x, y: pos.y, rotate: pos.rotate, scale: 1, opacity: 1 };
    }
    if (animationVariant === 'stackRight') {
      const pos = getRightStackAbsolutePosition(index);
      return { x: pos.x, y: pos.y, rotate: pos.rotate, scale: 1, opacity: 1 };
    }
    return undefined; // Use variant-based animation for arc, hidden, etc.
  };
  
  // Determine animate value: explicit position object or variant string
  const animateValue = getTargetPosition() ?? animationVariant;

  return (
    <motion.div
      layoutId={`rtb-card-${cardId}`}
      className={cardClasses}
      variants={cardLayoutVariants}
      initial={getInitialPosition()}
      animate={animateValue}
      exit="exit"
      custom={{ index, total }}
      transition={{ type: 'spring', stiffness: 300, damping: 25 }}
      style={{ 
        zIndex,
        position: 'absolute',
        width: '115px',
        perspective: 1000,
      }}
      onClick={onClick}
      whileTap={onClick ? { scale: 0.98 } : undefined}
      onAnimationComplete={(definition) => {
        // Only fire callback once
        // When using absolute positions, definition is the target object, not a variant string
        // So we check if callback hasn't fired yet
        if (onLayoutAnimationComplete && !layoutCallbackFiredRef.current) {
          // For variant-based animation, check if definition matches target
          // For object-based animation (useAbsolutePosition), just fire on any completion
          if (useAbsolutePosition || definition === animationVariant) {
            layoutCallbackFiredRef.current = true;
            onLayoutAnimationComplete();
          }
        }
      }}
    >
      {/* Inner wrapper for 3D flip animation */}
      <motion.div
        className="rtb-card-inner"
        variants={cardFlipVariants}
        initial={isRevealed ? 'faceUp' : 'faceDown'}
        animate={flipVariant}
        onAnimationComplete={(definition) => {
          // Only fire callback when transitioning to faceUp during flip
          if (flipStartedRef.current && 
              onFlipComplete && 
              definition === 'faceUp') {
            flipStartedRef.current = false;
            onFlipComplete();
          }
        }}
        style={{
          width: '100%',
          height: '100%',
          position: 'relative',
          transformStyle: 'preserve-3d',
        }}
      >
        {/* Back face - placeholder (visible when faceDown) */}
        <div 
          className="rtb-card-face rtb-card-back"
          style={{
            position: 'absolute',
            width: '100%',
            height: '100%',
            backfaceVisibility: 'hidden',
            WebkitBackfaceVisibility: 'hidden',
            transform: 'rotateY(0deg)',
          }}
        >
          <div className="rtb-card-placeholder">
            <span className="rtb-card-question">?</span>
          </div>
        </div>
        
        {/* Front face - revealed card (visible when faceUp) */}
        <div 
          className="rtb-card-face rtb-card-front"
          style={{
            position: 'absolute',
            width: '100%',
            height: '100%',
            backfaceVisibility: 'hidden',
            WebkitBackfaceVisibility: 'hidden',
            transform: 'rotateY(180deg)',
          }}
        >
          {card.image_b64 ? (
            <>
              <img
                src={`data:image/png;base64,${card.image_b64}`}
                alt={card.title || 'Card'}
                className="rtb-card-image"
              />
              <div className={`rtb-card-rarity rtb-rarity-${card.rarity.toLowerCase()}`}>
                {card.rarity}
              </div>
            </>
          ) : (
            // Fallback if no image yet (shouldn't happen when revealed)
            <div className="rtb-card-placeholder rtb-card-placeholder-empty" />
          )}
        </div>
      </motion.div>
    </motion.div>
  );
};

// =============================================================================
// MEMOIZATION
// =============================================================================

/**
 * Memoized version to prevent unnecessary re-renders
 * Only re-renders when card state actually changes
 */
export default React.memo(RTBCard, (prevProps, nextProps) => {
  return (
    prevProps.cardId === nextProps.cardId &&
    prevProps.variant === nextProps.variant &&
    prevProps.initialVariant === nextProps.initialVariant &&
    prevProps.index === nextProps.index &&
    prevProps.total === nextProps.total &&
    prevProps.initialIndex === nextProps.initialIndex &&
    prevProps.initialTotal === nextProps.initialTotal &&
    prevProps.isRevealed === nextProps.isRevealed &&
    prevProps.isSelected === nextProps.isSelected &&
    prevProps.isLosing === nextProps.isLosing &&
    prevProps.isTop === nextProps.isTop &&
    prevProps.isFlipping === nextProps.isFlipping &&
    prevProps.skipInitialAnimation === nextProps.skipInitialAnimation &&
    prevProps.zIndex === nextProps.zIndex &&
    prevProps.card.card_id === nextProps.card.card_id &&
    prevProps.card.rarity === nextProps.card.rarity &&
    prevProps.card.image_b64 === nextProps.card.image_b64
  );
});

// Also export the non-memoized version for testing
export { RTBCard };
