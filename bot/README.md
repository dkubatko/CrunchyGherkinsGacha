# Crunchy Gherkins Bot Backend

## Database migrations

This project now uses [Alembic](https://alembic.sqlalchemy.org/) to manage the SQLite schema. The migration tooling is configured under `bot/alembic`.

### Installing dependencies

From the `bot` directory install the Python requirements (Alembic and SQLAlchemy are already listed):

```bash
pip install -r requirements.txt
```

### Running migrations

The bot automatically applies migrations on startup via the helper in `utils/database.py`, so a normal launch will keep the schema current. You can also run migrations manually:

```bash
alembic -c alembic.ini upgrade head
```

### Baseline an existing database

If you already have a populated SQLite database that predates Alembic, the startup logic detects the existing `cards`/`user_rolls` tables and stamps the baseline revision (`20240924_0001`) automatically before applying any newer migrations. You can do the same manually:

```bash
alembic -c alembic.ini stamp 20240924_0001
alembic -c alembic.ini upgrade head
```

### Tracking Telegram user IDs

Revision `20240924_0002` introduces a `user_id` column on the `cards` table. The migration backfills existing cards using a static username → Telegram user ID map (see the migration script for the exact values) and new claims automatically record the user’s Telegram ID.

### Chats mapping

Revision `20240924_0003` adds a `chats` table that links the configured `GROUP_CHAT_ID` to every known Telegram user ID from the same map used above. A fresh upgrade will create one row per user for the group chat so future features can resolve membership quickly.

### User profiles

Revision `20240924_0004` introduces a `users` table (`user_id`, `username`, `display_name`, `profile_imageb64`). The migration seeds it with known Telegram IDs and usernames. Run the helper below after upgrading to populate display names and profile images from `data/base_images`:

```bash
python tools/backfill_user_profiles.py
```

The `/profile` DM command lets players upload a display name and portrait. The `/roll` and `/reroll` commands now pull their base images from a random enrolled user in the active chat who has supplied both a display name and portrait. If no one qualifies yet, the bot prompts the chat to DM `/profile` before trying again.

### SQLite compatibility

Alembic runs with `render_as_batch=True`, which enables schema migrations against SQLite. No extra database engine is required; the existing `DB_PATH` configuration continues to work.

## Spin Reward Economics

When players burn cards using `/burn <card_id>`, they receive spins based on the card's rarity. The spin rewards are calculated to maintain expected value equilibrium across rarities, using the following formula:

$$N_r = \frac{(w_L / w_r)}{p \times \sum(w_i \times (w_L / w_i))}$$

Where:

| Symbol | Description |
|--------|-------------|
| $N_r$ | Spins granted for burning a card of rarity $r$ |
| $w_r$ | Drop probability (weight) of rarity $r$ |
| $w_L$ | Drop probability of the Legendary rarity (used as value baseline = 1) |
| $p$ | Per-spin card win probability (e.g. 0.025 = 2.5%) |
| $\sum(...)$ | Summation over all rarities |

### Example Calculation

With the current configuration:

- **Card win chance per spin**: $p = 0.025$
- **Rarity drop weights**:
  - Common: $w_{Common} = 0.55$
  - Rare: $w_{Rare} = 0.25$
  - Epic: $w_{Epic} = 0.15$
  - Legendary: $w_{Legendary} = 0.05$
- **Sum of weighted values**: $\sum(w_i \times (w_L / w_i)) = 0.2$

This yields the following theoretical spin rewards:

| Rarity | Theoretical Spins ($N_r$) | Calculation |
|--------|---------------------------|-------------|
| Common | 18 | $(0.05 / 0.55) / (0.025 \times 0.2)$ |
| Rare | 40 | $(0.05 / 0.25) / (0.025 \times 0.2)$ |
| Epic | 67 | $(0.05 / 0.15) / (0.025 \times 0.2)$ |
| Legendary | 200 | $(0.05 / 0.05) / (0.025 \times 0.2)$ |

### Actual Implementation

The actual spin rewards configured in `config.json` are rounded for better user perception:

| Rarity | Configured Spins | Notes |
|--------|------------------|-------|
| Common | 20 | Rounded from 18 |
| Rare | 40 | Matches theoretical |
| Epic | 80 | Rounded from 67 |
| Legendary | 150 | Adjusted from 200 |

These values ensure that burning cards maintains approximate expected value equilibrium while providing intuitive, round numbers for players.

## Chat commands

- `/balance [@username]` — Displays the remaining claim points in the current chat. If you omit the argument it reports your own balance; otherwise it resolves the provided username (must be enrolled in the chat) and shows their balance. Claim balances are scoped per chat, so this command only works in group chats.
