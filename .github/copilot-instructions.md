# Crunchy Gherkins Gacha Bot — Agent Instructions

> **DO NOT** build the app, run tests, or execute commands unless the prompt explicitly asks for it.

---

## What This Project Is

A **Telegram-based gacha card game** where users collect AI-generated cards featuring characters with random modifiers and rarities.

### Core Gameplay Loop
1. **Rolling**: Users `/roll` once per cooldown period to generate a new card with AI-generated art (via Google Gemini)
2. **Claiming**: Rolled cards appear in chat; any enrolled user can `/claim` them using claim points
3. **Collection**: Users build collections viewable in a Telegram Mini App
4. **Trading**: Users can trade cards with each other
5. **Casino**: Users spend "spins" (earned by burning cards) on casino games to win more cards

### Card System
- **Rarities**: Common → Rare → Epic → Legendary → Unique (each with different weights, costs, rewards)
- **Modifiers**: Random adjectives/themes applied to base character names
- **Seasons**: Cards belong to seasons; only current-season cards can be claimed
- **Locking**: Users can lock cards to prevent accidental trading/burning

### Modifier Keyword Rubric (observed from `bot/data/modifiers/')
- **Primary selection factor**: Choose keywords by how much they *transform the generated image* when paired with a character and how *impactful, interesting and/or appealing* the combo feels to users.
- **Per-set theme consistency**: Each YAML file defines a tight theme (e.g., food, anime, horror) and keywords stay within that theme.
- **Common**: Mundane, non-transformative, or low-impact descriptors with minimal visual/novelty appeal (e.g., “Hiking”-style concepts).
- **Rare**: More specific or recognizable concepts that add some visual flavor or identity but aren’t yet show-stoppers.
- **Epic**: Strongly evocative, visually distinctive, or meta-leaning concepts that materially change the image’s vibe.
- **Legendary**: Most interesting, meta-ironic, or highly transformative/visually impactful keywords; flagship icons or deities; very small lists, sometimes empty.
- **Formatting**: Title case is typical, with occasional numerals/symbols; mixed languages are allowed; lists are automatically alphabetized and de-duplicated on bot start.
- **Source/activation**: Some sets use `source: roll` (gated), and some files include `active: false` for seasonal deactivation.

### Casino Games
- **Slots**: Match 3 symbols to win cards; symbols are user avatars + character icons
- **Minesweeper**: Bet a card, reveal tiles without hitting mines to win a card of equal/higher rarity
- **Ride the Bus**: Bet spins and guess card rarities for multiplying payouts

### Currency System
- **Claim Points**: Spent to claim rolled cards; regenerate over time
- **Spins**: Earned by burning cards; spent on casino games

---

## Architecture Overview

### Stack
- **Backend** (`bot/`): Python with `python-telegram-bot` + FastAPI
- **Database**: SQLite with SQLAlchemy ORM + Alembic migrations
- **Frontend** (`miniapp/`): React + Vite + TypeScript, runs as Telegram Mini App
- **Image Generation**: Google Gemini API

### Two Entry Points
1. **Telegram Bot** (`bot/bot.py`): Handles slash commands in group chats (`/roll`, `/claim`, `/trade`, etc.)
2. **REST API** (`bot/api/`): Powers the Mini App (collection viewing, casino games, card management)

### Data Flow
```
Telegram Chat                    Mini App (WebView)
     │                                  │
     ▼                                  ▼
Bot Handlers ──────────────────► FastAPI Endpoints
     │                                  │
     └──────────► Service Layer ◄───────┘
                       │
                       ▼
              SQLite Database
```

---

## Design Principles

### Backend Organization
- **Handlers** (`bot/handlers/`): Telegram command handlers, thin layer that delegates to services
- **API Routers** (`bot/api/routers/`): FastAPI endpoints, organized by domain
- **Services** (`bot/utils/services/`): All business logic lives here; handlers/routers never do raw DB queries
- **Models** (`bot/utils/models.py`): SQLAlchemy ORM models
- **Schemas**: Pydantic models for API request/response validation

### Handler Decorators
Bot commands use decorators for auth/validation:
- `@verify_user` — user must be registered (via `/start`)
- `@verify_user_in_chat` — user must be enrolled in the current chat
- `@verify_admin` — admin-only commands
- `@prevent_concurrency` — prevents race conditions on user actions

### API Authentication
All Mini App API calls include `Authorization: tma <initData>` header. The backend validates this using Telegram's HMAC-SHA256 WebApp verification spec.

### Mini App Routing
The Mini App is launched with a `start_param` token that determines what view to show:
- Card view, collection view, or casino view
- Tokens are base64-encoded with a `tg1_` prefix
- Encoding happens in bot code, decoding in frontend

### Event System
User actions emit typed events (ROLL, CLAIM, BURN, SPIN, etc.) that:
- Get logged to an events table for analytics
- Trigger the achievement system to check for newly earned achievements

### Image Storage
- Card images stored as base64 in a separate `card_images` table
- Thumbnails auto-generated at 1/4 scale for grid views
- Frontend caches images in memory + IndexedDB

---

## Configuration

### Environment Variables
- Bot tokens, API keys, admin username, Mini App URLs configured via `.env` files
- Debug mode (`--debug` flag) uses separate test bot token and endpoints

### Game Constants (`bot/config.json`)
All tunable game values: rarity weights, costs, rewards, casino odds, cooldowns, etc.

---

## Development

### Running Locally
```bash
# Bot with debug mode
python bot/bot.py --debug

# API server
uvicorn bot.api.server:app --reload

# Mini App dev server
cd miniapp && npm run dev
```

### Database Changes
1. Modify models in `bot/utils/models.py`
2. Create Alembic migration: `cd bot && alembic revision -m "description"`
3. Migrations auto-run on startup

---

## Key Conventions

- **Never bypass the service layer** — all DB operations go through `utils/services/`
- **Use existing decorators** — don't reinvent auth/validation in handlers
- **Extend ApiService class** — don't scatter fetch calls in frontend components
- **Typed events** — use the event enums when logging actions
- **Token encoding** — mini app launch params must use the established token format
