# Poker Database Schema

## Overview
Two-table design to support multiplayer poker games with WebSocket updates.

---

## Table: `poker_games`

Stores the state of each poker game instance.

### Columns

| Column | Type | Default | Description |
|--------|------|---------|-------------|
| `id` | INTEGER | AUTO | Primary key |
| `chat_id` | STRING | - | Telegram chat where game is played |
| `status` | STRING | 'waiting' | Game state (see statuses below) |
| `pot` | INTEGER | 0 | Total pot in spins |
| `current_bet` | INTEGER | 0 | Current bet amount players must match |
| `min_betting_balance` | INTEGER | NULL | Equalized betting balance for all players |
| `community_cards` | STRING (JSON) | '[]' | Array of `{source_id, source_type, rarity}` objects |
| `countdown_start_time` | DATETIME | NULL | When 60s countdown began |
| `current_player_turn` | INTEGER | NULL | User ID whose turn it is |
| `dealer_position` | INTEGER | NULL | Seat index of dealer (for turn order) |
| `created_at` | DATETIME | - | Game creation timestamp |
| `updated_at` | DATETIME | - | Last update timestamp |
| `completed_at` | DATETIME | NULL | When game finished |

### Game Statuses
- **`waiting`** - Waiting for players to join (< 2 players)
- **`countdown`** - 60s countdown active (≥ 2 players)
- **`pre_flop`** - Betting before flop (hole cards dealt, no community cards)
- **`flop`** - Betting after flop (3 community cards revealed)
- **`turn`** - Betting after turn (4 community cards revealed)
- **`river`** - Betting after river (all 5 community cards revealed)
- **`showdown`** - Reveal and determine winner
- **`completed`** - Game finished, payouts done

### Indexes
- `idx_poker_games_chat_status` - Fast lookup of active games per chat
- `idx_poker_games_status` - Filter by game status
- `idx_poker_games_created` - Time-based queries

---

## Table: `poker_players`

Stores individual player state within a game.

### Columns

| Column | Type | Default | Description |
|--------|------|---------|-------------|
| `id` | INTEGER | AUTO | Primary key |
| `game_id` | INTEGER | - | Foreign key to poker_games |
| `user_id` | INTEGER | - | Telegram user ID |
| `chat_id` | STRING | - | Telegram chat ID |
| `seat_position` | INTEGER | - | Position around table (0-indexed) |
| `spin_balance` | INTEGER | - | Player's total spins when joined |
| `betting_balance` | INTEGER | - | Equalized balance for this game |
| `current_bet` | INTEGER | 0 | Amount bet in current betting round |
| `total_bet` | INTEGER | 0 | Total amount bet across all rounds |
| `hole_cards` | STRING (JSON) | '[]' | Array of 2 cards: `[{source_id, source_type, rarity}, ...]` |
| `status` | STRING | 'active' | Player state (see statuses below) |
| `last_action` | STRING | NULL | Last action: check, raise, fold, all_in |
| `joined_at` | DATETIME | - | When player joined game |
| `updated_at` | DATETIME | - | Last update timestamp |

### Player Statuses
- **`active`** - Still playing, can take actions
- **`folded`** - Folded hand, out of current game
- **`all_in`** - Bet entire betting_balance, no more actions
- **`out`** - Removed from game (disconnected or insufficient balance)

### Indexes
- `idx_poker_players_game` - All players in a game
- `idx_poker_players_user` - All games for a user
- `idx_poker_players_game_user` - Unique lookup per game+user
- `idx_poker_players_user_chat` - User's games in specific chat

---

## JSON Field Formats

### `community_cards` / `hole_cards`
```json
[
  {"source_id": 5, "source_type": "character", "rarity": "legendary"},
  {"source_id": 42, "source_type": "user", "rarity": "common"}
]
```

**Fields:**
- `source_id` - ID of the character or user
- `source_type` - Either `"character"` or `"user"`
- `rarity` - Card rarity (e.g., "common", "rare", "epic", "legendary")

---

## WebSocket Integration Notes

### Real-time Updates Triggered By:
1. **Player joins** → Update `poker_players`, broadcast seat update
2. **Countdown starts** → Update `status='countdown'`, `countdown_start_time`
3. **Game starts** → Deal cards, update `status='pre_flop'`, set `current_player_turn`
4. **Player action** → Update `current_bet`, `last_action`, advance `current_player_turn`
5. **Round advances** → Reveal community cards, update `status` (flop/turn/river)
6. **Showdown** → Calculate winner, update `pot`, player balances
7. **Game ends** → Update `status='completed'`, `completed_at`

### WebSocket Message Types (Future)
- `PLAYER_JOINED` - New player at table
- `COUNTDOWN_STARTED` - Timer began
- `GAME_STARTED` - Cards dealt
- `PLAYER_ACTION` - Check/raise/fold/all-in
- `TURN_CHANGED` - Next player's turn
- `ROUND_ADVANCED` - New community cards revealed
- `GAME_ENDED` - Winner determined

---

## Query Patterns

### Get active game in chat
```sql
SELECT * FROM poker_games 
WHERE chat_id = ? AND status NOT IN ('completed')
ORDER BY created_at DESC LIMIT 1
```

### Get all players in game
```sql
SELECT * FROM poker_players 
WHERE game_id = ? 
ORDER BY seat_position
```

### Check if user is in game
```sql
SELECT * FROM poker_players 
WHERE game_id = ? AND user_id = ? AND status != 'out'
```

### Get active players (not folded/out)
```sql
SELECT * FROM poker_players 
WHERE game_id = ? AND status IN ('active', 'all_in')
```

---

## Migration File
- **File:** `20251018_0029_create_poker_tables.py`
- **Revises:** `20251016_0028`
- **Tables Created:** `poker_games`, `poker_players`
- **Indexes:** 7 indexes total for query optimization

---

_Last Updated: October 18, 2025_
