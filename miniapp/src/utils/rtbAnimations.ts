/**
 * RideTheBus Animation Utilities
 * 
 * Contains layout position calculators, timing constants, and Framer Motion variants
 * for card animations in the RideTheBus minigame.
 */

import type { Variants } from 'framer-motion';

// =============================================================================
// TIMING CONSTANTS
// =============================================================================

/** Duration for layout transitions (fan ↔ stacks) in seconds */
export const RTB_LAYOUT_DURATION = 0.5;

/** Duration for card flip animation in seconds */
export const RTB_FLIP_DURATION = 0.4;

/** Stagger delay between cards in seconds */
export const RTB_STAGGER_DELAY = 0.08;

/** Spring configuration for smooth, natural motion */
export const RTB_SPRING_CONFIG = {
  type: 'spring' as const,
  stiffness: 300,
  damping: 25,
};

/** Tween configuration for controlled timing */
export const RTB_TWEEN_CONFIG = {
  type: 'tween' as const,
  duration: RTB_LAYOUT_DURATION,
  ease: [0.25, 0.46, 0.45, 0.94] as const, // easeOutQuad
};

// =============================================================================
// LAYOUT POSITION CALCULATORS
// =============================================================================

export interface CardPosition {
  x: number;
  y: number;
  rotate: number;
  scale?: number;
}

/**
 * Calculate card position in arc/fan layout
 * 
 * Creates a fan effect by rotating cards around a pivot point below the cards.
 * Since Framer Motion doesn't support transform-origin with its x/y/rotate,
 * we calculate the actual position each card should be at after rotation.
 * 
 * The math: 
 * - Cards rotate around a point (pivot) located below the card center
 * - After rotation, we calculate where the card center ends up
 * - x = pivot_distance * sin(angle)
 * - y = pivot_distance * (1 - cos(angle)) - this creates the arc curve
 */
export function getArcPosition(index: number, total: number): CardPosition {
  const middleIndex = (total - 1) / 2;
  const offsetFromMiddle = index - middleIndex;
  
  // Rotation angle per card position (in degrees)
  const rotationPerCard = 8;
  const rotationDeg = offsetFromMiddle * rotationPerCard;
  const rotationRad = (rotationDeg * Math.PI) / 180;
  
  // Distance from card center to rotation pivot (below the card)
  // Smaller value = tighter arc, less horizontal spread
  const pivotDistance = 420;
  
  // Calculate actual position after rotation around the pivot
  // x: horizontal displacement from center
  // y: vertical displacement - outer cards drop down creating the arc
  const x = pivotDistance * Math.sin(rotationRad);
  const y = pivotDistance * (1 - Math.cos(rotationRad));
  
  // Vertical offset to lift the entire arc up
  const baseYOffset = -10;
  
  return {
    x,
    y: y + baseYOffset,
    rotate: rotationDeg,
    scale: 1,
  };
}

// =============================================================================
// STACK LAYOUT CONSTANTS
// =============================================================================

/** Width of a single card stack container in pixels */
export const STACK_WIDTH = 115;

/** Gap between left and right stacks in pixels */
export const STACK_GAP = 40;

/** 
 * Distance from center of .rtb-main-cards to center of each stack
 * = (STACK_WIDTH + STACK_GAP) / 2 = (115 + 40) / 2 = 77.5
 */
export const STACK_CENTER_OFFSET = (STACK_WIDTH + STACK_GAP) / 2;

// =============================================================================
// RELATIVE STACK POSITION CALCULATORS (within stack container)
// =============================================================================

/**
 * Calculate card position in left stack (revealed cards)
 * Cards stack with slight offset and rotation for depth effect
 * Returns position RELATIVE to the left stack container
 */
export function getLeftStackPosition(index: number, totalInStack: number): CardPosition {
  const depthFromTop = totalInStack - 1 - index;
  
  return {
    x: -depthFromTop * 6,     // Offset left for depth
    y: 0,
    rotate: -depthFromTop * 4, // Slight counter-clockwise rotation
    scale: 1,
  };
}

/**
 * Calculate card position in right stack (unrevealed cards)
 * Cards stack with offset in opposite direction
 * Returns position RELATIVE to the right stack container
 */
export function getRightStackPosition(index: number): CardPosition {
  return {
    x: index * 6,       // Offset right for depth
    y: 0,
    rotate: index * 4,  // Slight clockwise rotation
    scale: 1,
  };
}

// =============================================================================
// ABSOLUTE STACK POSITION CALCULATORS (relative to .rtb-main-cards center)
// =============================================================================

/**
 * Calculate card position in left stack with absolute offset from container center
 * Used for animating cards BETWEEN stacks
 */
export function getLeftStackAbsolutePosition(index: number, totalInStack: number): CardPosition {
  const relativePos = getLeftStackPosition(index, totalInStack);
  
  return {
    x: -STACK_CENTER_OFFSET + relativePos.x,  // Left of center + depth offset
    y: relativePos.y,
    rotate: relativePos.rotate,
    scale: 1,
  };
}

/**
 * Calculate card position in right stack with absolute offset from container center
 * Used for animating cards BETWEEN stacks
 */
export function getRightStackAbsolutePosition(index: number): CardPosition {
  const relativePos = getRightStackPosition(index);
  
  return {
    x: STACK_CENTER_OFFSET + relativePos.x,  // Right of center + depth offset
    y: relativePos.y,
    rotate: relativePos.rotate,
    scale: 1,
  };
}

// =============================================================================
// FRAMER MOTION VARIANTS
// =============================================================================

/**
 * Container variants for staggered children animations
 */
export const cardContainerVariants: Variants = {
  hidden: {},
  visible: {
    transition: {
      staggerChildren: RTB_STAGGER_DELAY,
      delayChildren: 0.1,
    },
  },
  exit: {
    transition: {
      staggerChildren: RTB_STAGGER_DELAY / 2,
      staggerDirection: -1,
    },
  },
};

/**
 * Card layout variants for different positions
 * Use with `custom` prop to pass { index, total, side } for dynamic positioning
 */
export const cardLayoutVariants: Variants = {
  // Initial hidden state
  hidden: {
    opacity: 0,
    scale: 0.8,
    y: 20,
  },
  
  // Arc/fan layout (betting phase, finished phase)
  arc: (custom: { index: number; total: number }) => {
    const pos = getArcPosition(custom.index, custom.total);
    return {
      x: pos.x,
      y: pos.y,
      rotate: pos.rotate,
      scale: pos.scale,
      opacity: 1,
      transition: RTB_SPRING_CONFIG,
    };
  },
  
  // Arc layout with selected card shifted up
  arcSelected: (custom: { index: number; total: number }) => {
    const pos = getArcPosition(custom.index, custom.total);
    // Shift card up slightly when selected
    const selectedYOffset = -15;
    return {
      x: pos.x,
      y: pos.y + selectedYOffset,
      rotate: pos.rotate,
      scale: 1.02,
      opacity: 1,
      transition: {
        type: 'spring' as const,
        stiffness: 400,
        damping: 25,
      },
    };
  },
  
  // Left stack (revealed cards during gameplay)
  stackLeft: (custom: { index: number; total: number }) => {
    const pos = getLeftStackPosition(custom.index, custom.total);
    return {
      x: pos.x,
      y: pos.y,
      rotate: pos.rotate,
      scale: pos.scale,
      opacity: 1,
      transition: RTB_SPRING_CONFIG,
    };
  },
  
  // Right stack (unrevealed cards during gameplay)
  stackRight: (custom: { index: number; total: number }) => {
    const pos = getRightStackPosition(custom.index);
    return {
      x: pos.x,
      y: pos.y,
      rotate: pos.rotate,
      scale: pos.scale,
      opacity: 1,
      transition: RTB_SPRING_CONFIG,
    };
  },
  
  // Exit animation
  exit: {
    opacity: 0,
    scale: 0.85,
    transition: {
      duration: 0.3,
    },
  },
};

/**
 * Card flip variants for reveal animation
 * Apply to inner card content wrapper
 * 
 * The back face (placeholder) is at CSS rotateY(0deg)
 * The front face (image) is at CSS rotateY(180deg)
 * 
 * When inner wrapper is at rotateY: 0 → back shows (placeholder visible)
 * When inner wrapper is at rotateY: 180 → front shows (image visible)
 */
export const cardFlipVariants: Variants = {
  // Card face down - showing placeholder (back face)
  faceDown: {
    rotateY: 0,
    transition: {
      duration: RTB_FLIP_DURATION,
      ease: 'easeInOut',
    },
  },
  
  // Card face up - showing image (front face)
  faceUp: {
    rotateY: 180,
    transition: {
      duration: RTB_FLIP_DURATION,
      ease: 'easeInOut',
    },
  },
};

/**
 * Card face variants (for front/back of flip)
 * These control visibility during the flip
 */
export const cardFaceVariants: Variants = {
  visible: {
    opacity: 1,
    transition: { duration: 0 },
  },
  hidden: {
    opacity: 0,
    transition: { duration: 0 },
  },
};

/**
 * Selected card highlight variants
 */
export const cardSelectedVariants: Variants = {
  idle: {
    scale: 1,
    boxShadow: '0 4px 12px rgba(0, 0, 0, 0.3)',
  },
  selected: {
    scale: 1.03,
    y: -3,
    boxShadow: '0 0 16px 4px rgba(255, 215, 0, 0.6), 0 6px 20px rgba(0, 0, 0, 0.5)',
    transition: {
      type: 'spring',
      stiffness: 400,
      damping: 20,
    },
  },
};

/**
 * Losing card glow variants
 */
export const cardLosingVariants: Variants = {
  idle: {
    boxShadow: '0 4px 12px rgba(0, 0, 0, 0.3)',
  },
  losing: {
    boxShadow: [
      '0 0 0 0 rgba(255, 80, 80, 0)',
      '0 0 12px 4px rgba(255, 80, 80, 0.6), 0 0 20px 6px rgba(220, 50, 50, 0.3)',
    ],
    transition: {
      duration: 0.4,
      ease: 'easeOut',
    },
  },
};

// =============================================================================
// UTILITY FUNCTIONS
// =============================================================================

/**
 * Get the appropriate variant name based on game phase and card state
 */
export function getCardVariant(
  phase: 'betting' | 'playing' | 'finished',
  side?: 'left' | 'right'
): string {
  if (phase === 'betting' || phase === 'finished') {
    return 'arc';
  }
  return side === 'left' ? 'stackLeft' : 'stackRight';
}

/**
 * Check if card is revealed (has image data)
 */
export function isCardRevealed(card: { rarity: string; image_b64: string | null }): boolean {
  return card.rarity !== '???' && card.image_b64 !== null;
}

// =============================================================================
// UNIFIED CARD IDENTITY SYSTEM
// =============================================================================

/**
 * Represents a card's stable identity throughout all animation phases.
 * 
 * The key insight: a card moving from the right stack to the left stack
 * is the SAME card and should have the SAME React key and Framer Motion layoutId.
 * This prevents re-mount animations when cards transition between stacks.
 */
export interface RTBCardIdentity {
  /** 
   * Stable unique identifier for this card slot.
   * Format: `rtb-slot-{slotIndex}` where slotIndex is 0-based from game start.
   * This ID remains constant regardless of which stack the card is in.
   */
  id: string;
  
  /**
   * The original slot index (0 to totalCards-1).
   * Slot 0 is revealed first, slot N-1 is revealed last.
   */
  slotIndex: number;
  
  /**
   * Current location of this card.
   * - 'unrevealed': In right stack, not yet flipped
   * - 'revealed': In left stack, face up
   * - 'animating': Currently being flipped/moved
   */
  location: 'unrevealed' | 'revealed' | 'animating';
  
  /**
   * The actual card data once revealed (null while unrevealed)
   */
  cardId: number | null;
}

/**
 * Generate stable card identities for a game session.
 * Call this once when the game loads/starts, not on every render.
 * 
 * @param totalCards - Total number of cards in the game
 * @param revealedCardIds - Array of card IDs that have been revealed (in order)
 * @returns Array of card identities, ordered by slot index
 */
export function generateCardIdentities(
  totalCards: number,
  revealedCardIds: number[]
): RTBCardIdentity[] {
  const identities: RTBCardIdentity[] = [];
  
  for (let slotIndex = 0; slotIndex < totalCards; slotIndex++) {
    const isRevealed = slotIndex < revealedCardIds.length;
    
    identities.push({
      id: `rtb-slot-${slotIndex}`,
      slotIndex,
      location: isRevealed ? 'revealed' : 'unrevealed',
      cardId: isRevealed ? revealedCardIds[slotIndex] : null,
    });
  }
  
  return identities;
}

/**
 * Update card identities when a new card is revealed.
 * Returns a new array (immutable update).
 * 
 * @param identities - Current card identities
 * @param revealedCardId - The card_id of the newly revealed card
 * @param animating - Whether the card is currently animating (flipping/moving)
 * @returns Updated identities array
 */
export function updateCardIdentityOnReveal(
  identities: RTBCardIdentity[],
  revealedCardId: number,
  animating: boolean = false
): RTBCardIdentity[] {
  // Find the first unrevealed slot
  const slotToReveal = identities.findIndex(id => id.location === 'unrevealed');
  
  if (slotToReveal === -1) {
    console.warn('No unrevealed slots left to reveal');
    return identities;
  }
  
  return identities.map((identity, index) => {
    if (index === slotToReveal) {
      return {
        ...identity,
        location: animating ? 'animating' : 'revealed',
        cardId: revealedCardId,
      };
    }
    return identity;
  });
}

/**
 * Mark an animating card as fully revealed (animation complete).
 * 
 * @param identities - Current card identities
 * @returns Updated identities array with animating cards marked as revealed
 */
export function completeCardAnimation(identities: RTBCardIdentity[]): RTBCardIdentity[] {
  return identities.map(identity => {
    if (identity.location === 'animating') {
      return { ...identity, location: 'revealed' };
    }
    return identity;
  });
}

/**
 * Get the React key for a card based on its stable identity.
 * This key should NEVER change during the card's lifecycle.
 * 
 * @param identity - The card's identity
 * @returns Stable React key string
 */
export function getCardKey(identity: RTBCardIdentity): string {
  return identity.id;
}

/**
 * Get the Framer Motion layoutId for a card.
 * Using the same value as the key ensures layout animations work correctly.
 * 
 * @param identity - The card's identity
 * @returns Stable layoutId string
 */
export function getCardLayoutId(identity: RTBCardIdentity): string {
  return identity.id;
}

/**
 * Split identities into left (revealed) and right (unrevealed) stacks.
 * Useful for rendering the two stacks separately.
 * 
 * @param identities - All card identities
 * @returns Object with leftStack and rightStack arrays
 */
export function splitByStack(identities: RTBCardIdentity[]): {
  leftStack: RTBCardIdentity[];
  rightStack: RTBCardIdentity[];
  animatingCard: RTBCardIdentity | null;
} {
  const leftStack: RTBCardIdentity[] = [];
  const rightStack: RTBCardIdentity[] = [];
  let animatingCard: RTBCardIdentity | null = null;
  
  for (const identity of identities) {
    if (identity.location === 'revealed') {
      leftStack.push(identity);
    } else if (identity.location === 'unrevealed') {
      rightStack.push(identity);
    } else if (identity.location === 'animating') {
      animatingCard = identity;
    }
  }
  
  return { leftStack, rightStack, animatingCard };
}

/**
 * Calculate the position index for a card within its current stack.
 * 
 * For left stack: index 0 is at bottom (first revealed), higher indices on top
 * For right stack: index 0 is on top (next to be revealed), higher indices at bottom
 * 
 * @param identity - The card's identity
 * @param allIdentities - All card identities for context
 * @returns The position index within the card's current stack
 */
export function getStackIndex(
  identity: RTBCardIdentity,
  allIdentities: RTBCardIdentity[]
): number {
  const { leftStack, rightStack } = splitByStack(allIdentities);
  
  if (identity.location === 'revealed') {
    return leftStack.findIndex(id => id.id === identity.id);
  } else if (identity.location === 'unrevealed') {
    return rightStack.findIndex(id => id.id === identity.id);
  } else {
    // Animating card - use its destination position (top of left stack)
    return leftStack.length;
  }
}
