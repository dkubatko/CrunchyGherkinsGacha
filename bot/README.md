# Crunchy Gherkins Bot Backend

Backend services for the Crunchy Gherkins gacha experience. The Telegram bot handles chat-facing gameplay while a FastAPI service powers a React/Vite mini-app that lets players browse, trade, burn, and lock their cards.

## System overview

- **Telegram bot** — Built with `python-telegram-bot`, it polls for chat commands, manages roll/claim workflows, and enforces per-chat claim and spin balances.
- **FastAPI server** — Shares the same process as the bot (threaded startup) and exposes authenticated JSON endpoints consumed by the mini-app and inline callbacks.
- **SQLite + Alembic** — A lightweight relational store managed through Alembic migrations at `bot/alembic`; migrations run automatically during bot startup.
- **Mini-app** — A Vite/React front-end embedded in Telegram via `WebAppInfo`, launched with bot-issued `tg1_...` tokens that scope users to their collections, single cards, or slots.

## Core gameplay loop

### Registration, profiles, and enrollment

- `/start` (DM): registers a Telegram user, ensuring a username exists before creating an entry in the `users` table.
- `/profile` (DM): updates display name and portrait; the bot stores the image as base64 for future card generation. In group chats the same command is reserved for the bot admin to seed permanent “characters”.
- `/enroll` (group): records that a registered user participates in the current chat so their claim balance and rolls are tracked per chat.

### Rolling and claiming cards

- `/roll` (group): once every 24 hours per chat, the bot selects a random eligible player/character profile, feeds it into `GeminiUtil`, and posts a generated card. Claiming consumes per-chat claim points; rerolling downgrades rarity and returns claim points to the previous owner when needed.
- `/claim` buttons: inline callbacks maintain card state, enforce enrollment, and handle reroll/lock cooldowns through `RolledCardManager`.
- `/balance` (group): reports both claim points and slot spins; in DMs the command is disabled because balances are scoped to chats.

### Managing the collection

- `/collection` (DM or group): shows paginated cards with quick access to the mini-app. Users can optionally inspect another player’s collection when invoked in chat.
- `/burn <card_id>`: grants spins based on rarity and deletes the card after confirmation.
- `/recycle <rarity>`: burns a batch of unlocked cards of the same rarity to mint an upgraded rarity card.
- `/lock <card_id>`: consumes a claim point to prevent rerolls (or unlocks without a refund). Inline lock buttons on newly claimed cards share the same logic.
- `/trade <your_card_id> <their_card_id>`: creates an inline confirmation flow that swaps ownership when accepted.

### Slots mini-game

- `/slots`: posts a button that opens the slots view of the mini-app. Spins are earned from burning cards, `/spins`, or claim wins. The mini-app verifies spins with the backend before awarding rewards.

### Mini-app integration

- The bot issues `tg1_` tokens (`u-`, `uc-`, `c-`, and `casino-` payloads) via `encode_miniapp_token`, `encode_single_card_token`, and `encode_casino_token` so the React app can authenticate with the FastAPI API.
- Inline “View in the app!” buttons accompany card galleries, giving players the same data set as the Telegram view with richer interactions.

## Telegram commands

| Command | Scope | Description |
| --- | --- | --- |
| `/start` | DM | Register the user; required before any other command works. |
| `/profile [display name]` | DM | Update display name and portrait for card generation. |
| `/profile <character name>` + photo | Group (admin) | Adds a reusable character portrait to the active chat. |
| `/delete <character_name>` | Group (admin) | Removes characters by name from the chat roster. |
| `/enroll` | Group | Enrolls the caller in the chat so claim balances and rolls are enabled. |
| `/slots` | Group | Sends a WebApp button that opens the slots mini-game for the chat. |
| `/roll` | Group | Generates a card (24h cooldown). Claiming is handled via inline buttons. |
| `/balance [@username]` | Group | Shows claim and spin balances for the caller or a specific enrolled user. |
| `/collection [@username]` | DM / Group | Browses the caller’s collection or another user’s collection (group only). Includes mini-app deep link. |
| `/stats [@username]` | DM / Group | Summarises owned cards by rarity plus current claim/spin balances. In DMs it only shows the caller. |
| `/trade <your_card_id> <their_card_id>` | Group | Requests a trade and posts accept/reject buttons to the chat. |
| `/lock <card_id>` | Group | Locks (or unlocks) a card from rerolls; locking consumes 1 claim point. |
| `/burn <card_id>` | Group | Burns a card to award spins after inline confirmation. |
| `/recycle <rarity>` | Group | Burns multiple unlocked cards of the same rarity to generate an upgraded card. |
| `/spins <amount>` | Group (admin) | Adds spins to all enrolled chat members (capped at 100 per call). |
| `/reload` | Group (admin) | Clears cached Telegram `file_id`s so cards upload fresh images next render. |
| `/set_thread` | Group (admin) | Binds the bot to the current forum topic for future notifications. |

Inline callback handlers also cover `claim_`, `reroll_`, `lock_`, `lockcard_`, `burn_`, `recycle_`, `trade_accept_`, `trade_reject_`, and collection navigation buttons.

## Mini-app experience

- **Current view**: Carousel of the player’s most recent cards with swipe navigation, grid toggle, share-to-chat shortcuts, and action panel buttons for burn, lock, and trade.
- **All cards view**: Filter and sort tools (rarity, owner, name, ID) with trade grid mode that hides owned duplicates. Fetches additional imagery via `/cards/images` batching.
- **Single card deep links**: Tokens starting with `c-` display one card without navigation or trading UI—used for share links and inline previews.
- **Trade workflow**: Selecting “Trade” transitions to a comparison grid; selecting a counter-card makes the API call and then closes the web app.
- **Burn & lock dialogs**: Provide confirmation screens, show expected spin rewards, and keep claim balances fresh by querying `/user/<id>/claims`.
- **Slots view**: Displays available symbols, consumes spins, runs verification with `/slots/verify`, and triggers card/claim payouts through dedicated endpoints.
- **Viewport management**: Locks the Telegram webview height and hides the back button during single-card or trade views to avoid layout jumps.

## Major design choices

- **Decorator-driven validation**: `@verify_user`, `@verify_user_in_chat`, and `@verify_admin` centralise checks for registration, chat enrollment, and admin privileges.
- **Tokenised mini-app access**: Only four payload shapes (`u-`, `uc-`, `c-`, and `casino-`) are supported; the React app parses them via `miniapp/src/utils/telegram.ts`, and the FastAPI backend validates `Authorization: tma <payload>` headers for every request.
- **Image lifecycle**: Card art is cached in SQLite (base64 + Telegram `file_id`), and `database.clear_all_file_ids` lets admins refresh media if Telegram invalidates cached uploads.
- **Rolling pipeline**: Card generation is orchestrated through `utils/rolling.generate_card_for_chat`, which relies on Gemini for image synthesis and on profiles contributed via `/profile` or admin characters.
- **Economy balance**: Claim balances live per chat, reset daily for spins, and integrate tightly with locking, recycling, and slots. `config.json` contains rarity weights, claim costs, and spin rewards.
- **Concurrent services**: The Telegram bot and FastAPI server share the same process; the server runs in a daemon thread so HTTP endpoints stay hot while the bot polls updates.

## Database migrations

This project uses [Alembic](https://alembic.sqlalchemy.org/) to manage the SQLite schema. Migration files live under `bot/alembic`.

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

The `/profile` DM command lets players upload a display name and portrait. The `/roll` and `/reroll` commands pull their base images from a random enrolled user in the active chat who has supplied both a display name and portrait. If no one qualifies yet, the bot prompts the chat to DM `/profile` before trying again.

### SQLite compatibility

Alembic runs with `render_as_batch=True`, which enables schema migrations against SQLite. No extra database engine is required; the existing `DB_PATH` configuration continues to work.

## Spin reward economics

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

### Example calculation

With the current configuration:

- **Card win chance per spin**: $p = 0.025$
- **Rarity drop weights**:
  - Common: $w_{Common} = 0.55$
  - Rare: $w_{Rare} = 0.25$
  - Epic: $w_{Epic} = 0.15$
  - Legendary: $w_{Legendary} = 0.05$
- **Sum of weighted values**: $\sum(w_i \times (w_L / w_i)) = 0.2$

This yields the following theoretical spin rewards:

| Rarity | Theoretical spins ($N_r$) | Calculation |
|--------|---------------------------|-------------|
| Common | 18 | $(0.05 / 0.55) / (0.025 \times 0.2)$ |
| Rare | 40 | $(0.05 / 0.25) / (0.025 \times 0.2)$ |
| Epic | 67 | $(0.05 / 0.15) / (0.025 \times 0.2)$ |
| Legendary | 200 | $(0.05 / 0.05) / (0.025 \times 0.2)$ |

### Actual implementation

The actual spin rewards configured in `config.json` are rounded for better user perception:

| Rarity | Configured spins | Notes |
|--------|------------------|-------|
| Common | 20 | Rounded from 18 |
| Rare | 40 | Matches theoretical |
| Epic | 80 | Rounded from 67 |
| Legendary | 150 | Adjusted from 200 |

These values ensure that burning cards maintains approximate expected value equilibrium while providing intuitive, round numbers for players.
