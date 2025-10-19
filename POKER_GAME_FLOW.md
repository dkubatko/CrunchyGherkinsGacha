# Poker Game Flow Documentation

## Overview
A Texas Hold'em-style poker game integrated into the Casino mini-app, where players bet spins to win character cards of various rarities.

---

## Game Flow

### 1. Entering the Poker Room
- Players navigate from Casino → Poker
- Upon entry, they see a round poker table displaying:
  - Current seated players (if any)
  - An active game in progress (if applicable)
  - A "Join" button to sit at the table

### 2. Joining a Table
**Requirements:**
- Minimum balance: **10 spins**
- Players can join at any time (except during active betting rounds)

**Behavior:**
- Player icon appears around the poker table
- If player has < 10 spins, they cannot join
- Players automatically keep their seats between games unless their balance drops below 10 spins

### 3. Spectating
- Players can watch games in progress
- Spectators see:
  - All revealed community cards
  - Other players' cards only when revealed/shown
  - Current pot size and betting actions
- Spectators cannot see hidden hole cards

### 4. Game Start Conditions
**Minimum Players:** 2 seated players

**Pre-Game Timer:**
- Once ≥2 players are seated, a **60-second countdown** begins
- New players can join during the countdown
- When timer expires OR all players ready, game starts

### 5. Buy-In & Betting Balance Equalization
**Entry Cost:**
- Fixed **1 spin** deducted from each player at game start
- No small blind / big blind structure
- All players pay the same entry fee

**Balance Equalization:**
- Each player's betting balance = `min(all players' spin balances)`
- This eliminates side pots entirely
- Example:
  - Player A: 50 spins → betting balance = 15
  - Player B: 15 spins → betting balance = 15
  - Player C: 100 spins → betting balance = 15
- Maximum amount any player can win/lose per game is their betting balance

### 6. Dealing Cards
**Hole Cards (Player Hands):**
- Each player receives **2 cards**
- Cards format: `{Character} + {Rarity}`
  - Example: "Legendary Daniel", "Common Ash"
- Character and rarity are randomized independently

**Community Cards:**
- 5 community cards dealt in stages (see Betting Rounds)
- Also format: `{Character} + {Rarity}`
- Randomized independently

### 7. Betting Rounds
Four betting rounds follow standard Texas Hold'em structure:

#### Round 1: Pre-Flop
- Players see their 2 hole cards
- No community cards revealed yet
- Betting begins

#### Round 2: Flop
- 3 community cards revealed
- Betting round

#### Round 3: Turn
- 4th community card revealed
- Betting round

#### Round 4: River
- 5th (final) community card revealed
- Final betting round

### 8. Player Actions
During each betting round, players can:

**Check:**
- Pass action to next player
- Only available if no bet is active

**Raise:**
- Increase the current bet
- Minimum raise: **2x the current bet**
- Cannot exceed player's betting balance
- Example: If current bet is 5 spins, minimum raise is to 10 spins

**All-In:**
- Bet entire betting balance
- Player has no further betting decisions
- Still participates in showdown

**Fold:**
- Forfeit hand and exit current game
- Loses any spins already bet
- Keeps table seat for next game (if balance ≥ 10 spins)

### 9. Winning & Hand Evaluation

**Matching Logic (TENTATIVE - Subject to Change):**
- Players match their 2 hole cards with the 5 community cards (7 cards total)
- Current rule: Most matching cards wins
- Priority hierarchy: **Character match > Rarity match**
  - Example: 3 character matches beats 4 rarity matches
- _Note: This may evolve to traditional poker hand rankings_

**Pot Distribution:**
- Winner(s) receive the entire pot
- Pot = (Entry fees × player count) + (all bets made during rounds)

### 10. Post-Game & Reset

**Automatic Seat Retention:**
- Players keep their seats automatically between games
- Exception: Players with < 10 spins are removed from table

**Next Game:**
- If ≥2 players remain seated → 60-second timer starts for next game
- If <2 players remain → table returns to waiting state
- New players can join during countdown

---

## Edge Cases & Rules

### Minimum Balance Enforcement
- Players must maintain ≥10 spins to stay seated
- Checked at end of each game
- Players below threshold are automatically removed

### Disconnections
- _TBD: Define behavior for disconnected players_

### Ties
- _TBD: Define tiebreaker rules for hand evaluation_

### Maximum Players
- _TBD: Define table capacity (e.g., 6-8 players max?)_

---

## Technical Notes

### Frontend State Management
- Track seated players dynamically
- Display community cards progressively (hidden → revealed)
- Show player actions in real-time
- Timer countdown UI

### Backend Requirements
- Game state machine (waiting → countdown → dealing → betting → showdown → payout)
- Card randomization (character + rarity)
- Betting balance calculation and validation
- Pot calculation and distribution
- Player balance updates

---

## Future Considerations
- Traditional poker hand rankings implementation
- Tournament mode
- Player statistics/leaderboards
- Animations for card dealing and pot collection
- Sound effects and haptic feedback

---

_Last Updated: October 18, 2025_
