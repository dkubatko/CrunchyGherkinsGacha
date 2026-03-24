# Crunchy Gherkins Gacha Bot — Agent Instructions

> **DO NOT** build the app, run tests, or execute commands unless the prompt explicitly asks for it.

> **IMPORTANT — Keeping this file current:** Whenever you make changes to this project (new features, refactors, schema changes, new files/directories, config changes, new commands, etc.), **update this file** to reflect the current state of the project. This ensures future agents always have an accurate overview. If a section below becomes outdated by your changes, fix it before finishing your task.

---

## What This Project Is

A **Telegram-based gacha card game** ("Crunchy Gherkins") where users collect AI-generated cards featuring characters with crafted aspect combinations and rarities.

### Core Gameplay Loop (Gacha 2.0 — Aspect-Based Card Crafting)
1. **Rolling**: Users `/roll` once per cooldown to generate either a **base character card** (10% chance) or an **aspect** (90% chance), with AI-generated art via Google Gemini
2. **Claiming**: Rolled items appear in chat; any enrolled user can `/claim` them using claim points
3. **Card Crafting**: Players `/equip` aspects onto base cards (up to 5 per card), naming the card and generating new AI art blending the character with equipped aspects — this is the core creative loop
4. **Collection**: Users build collections viewable in a Telegram Mini App
5. **Trading**: Users can trade cards with each other, or aspects with each other (no cross-type trades)
6. **Casino**: Users spend "spins" (earned by burning aspects) on casino mini-games to win more cards/aspects

### Card & Aspect System
- **Rarities**: Common → Rare → Epic → Legendary → Unique (each with different weights, costs, rewards)
- **Aspects**: Collectible themed keywords (e.g., "Rainy" from a "Weather" set) with unique AI-generated sphere art. Aspects have rarities and can only be equipped on cards of equal or higher rarity (except Unique aspects, which fit any card)
- **Unique Aspects**: Forged via `/create` by sacrificing 5 Legendary aspects; player chooses a custom name
- **Recycling**: Combine lower-rarity aspects into higher-rarity ones (3 Common→1 Rare, 3 Rare→1 Epic, 4 Epic→1 Legendary)
- **Seasons**: Cards and aspects belong to seasons; only current-season items can be claimed
- **Locking**: Users can lock cards/aspects to prevent accidental trading/burning
- **Sets**: Aspect definitions are organized into themed sets within seasons (managed via admin dashboard)

### Aspect Keyword Rubric (for aspect definition data)
- **Primary selection factor**: Choose keywords by how much they *transform the generated image* when paired with a character and how *impactful, interesting and/or appealing* the combo feels to users.
- **Per-set theme consistency**: Each set defines a tight theme (e.g., food, anime, horror) and keywords stay within that theme.
- **Common**: Mundane, non-transformative, or low-impact descriptors with minimal visual/novelty appeal.
- **Rare**: More specific or recognizable concepts that add some visual flavor or identity but aren't yet show-stoppers.
- **Epic**: Strongly evocative, visually distinctive, or meta-leaning concepts that materially change the image's vibe.
- **Legendary**: Most interesting, meta-ironic, or highly transformative/visually impactful keywords; flagship icons; very small lists, sometimes empty.
- **Formatting**: Title case is typical, with occasional numerals/symbols; mixed languages are allowed.

### Casino Games
- **Slots**: Spin 3 reels to win cards or aspects; symbols are user avatars + character icons. Megaspins (guaranteed win) occur every ~100 regular spins
- **Minesweeper**: Bet a card, reveal tiles on a 3×3 grid without hitting mines to win an aspect
- **Ride the Bus (RTB)**: Bet spins (10–50) and guess card rarities (higher/lower) through a progression of multipliers (2x → 3x → 5x → 10x); cash out anytime or risk it all. 9-hour cooldown after completion

### Currency System
- **Claim Points**: Spent to claim rolled cards/aspects; cost varies by rarity
- **Spins**: Earned by burning aspects (reward varies by rarity); spent on casino games
- **Daily Bonus**: Login streak progression awarding escalating spins (10→15→20→25→30→35→40 over 7 days)

---

## Architecture Overview

### Stack
- **Backend** (`bot/`): Python with `python-telegram-bot` + FastAPI
- **Database**: PostgreSQL with SQLAlchemy ORM + Alembic migrations (migrated from SQLite; uses psycopg v3 driver)
- **Frontend** (`miniapp/`): React + Vite + TypeScript, runs as Telegram Mini App
- **Image Generation**: Google Gemini API
- **Deployment**: Production uses a local Telegram Bot API server (`localhost:8081`); debug mode uses `api.telegram.org`

### Two Entry Points
1. **Telegram Bot** (`bot/bot.py`): Handles slash commands in group chats
2. **REST API** (`bot/api/server.py`): Powers the Mini App + admin dashboard

### Data Flow
```
Telegram Chat                    Mini App (WebView)        Admin Dashboard
     │                                  │                        │
     ▼                                  ▼                        ▼
Bot Handlers ──────────────────► FastAPI Endpoints ◄──── Admin Routers
     │                                  │                        │
     └──────────► Service Layer ◄───────┘────────────────────────┘
                       │
                       ▼
             PostgreSQL Database
```

---

## Project Structure

### Backend (`bot/`)
```
bot/
├── bot.py                    # Entry point — init, create app, register handlers, run polling
├── config.py                 # Bot startup config, initializes utilities
├── config.json               # All tunable game constants (rarities, odds, rewards, cooldowns)
├── core/
│   ├── application.py        # Factory: create_application() — debug vs production Telegram endpoints
│   └── handlers.py           # register_handlers() — wires all command & callback handlers
├── handlers/                 # Telegram command handlers (thin layer → services)
│   ├── user.py               # /start, /profile, /delete, /enroll, /unenroll
│   ├── rolling.py            # /roll (card/aspect), claim_/lock_/reroll_ callbacks
│   ├── cards.py              # /refresh, /equip + callbacks
│   ├── aspects.py            # /burn, /lock, /recycle, /create + callbacks
│   ├── collection.py         # /casino, /balance, /collection, /stats + navigation callbacks
│   ├── trade.py              # /trade, accept/reject callbacks for card & aspect trades
│   ├── admin.py              # /spins, /reload, /set_thread (admin-only)
│   └── helpers.py            # Handler utilities (logging, file ID saving, roll time calc)
├── api/
│   ├── server.py             # FastAPI app: CORS, rate limiting, router mounting, startup hooks
│   ├── config.py             # API config (debug/prod URLs, Gemini setup)
│   ├── helpers.py            # Auth validation (Telegram HMAC-SHA256, JWT for admin)
│   ├── limiter.py            # slowapi rate limiter instance
│   ├── background_tasks.py   # Async task processing (victory notifications, image gen)
│   └── routers/              # FastAPI endpoint modules
│       ├── cards.py          # Collection endpoints: GET /all, GET /{user_id}, GET /detail, images
│       ├── aspects.py        # Aspect endpoints: list, detail, images, burn, lock
│       ├── slots.py          # Slots game: spins, daily bonus, spin/verify/victory
│       ├── rtb.py            # Ride the Bus: game state, start, guess, cashout
│       ├── minesweeper.py    # Minesweeper: game state, create, update
│       ├── trade.py          # Trade endpoints: options, execute
│       ├── user.py           # User profile endpoint
│       ├── chat.py           # Chat utilities
│       ├── downloads.py      # Image download/export
│       ├── admin_auth.py     # Admin login (OTP + JWT)
│       ├── admin_sets.py     # Admin season/set management
│       └── admin_aspects.py  # Admin aspect definition CRUD
├── utils/
│   ├── models.py             # All SQLAlchemy ORM models (~24 tables)
│   ├── schemas.py            # Pydantic DTOs for API request/response validation
│   ├── database.py           # DB init + Alembic migration runner
│   ├── session.py            # SQLAlchemy engine/session factory (PostgreSQL via psycopg v3)
│   ├── decorators.py         # @verify_user, @verify_user_in_chat, @verify_admin, @prevent_concurrency
│   ├── events.py             # EventType enums, outcome enums (ROLL, CLAIM, BURN, SPIN, etc.)
│   ├── achievements.py       # Achievement system (observer pattern on events)
│   ├── rolling.py            # Roll logic (determine rarity, generate cards/aspects)
│   ├── roll_manager.py       # Complex roll orchestration
│   ├── gemini.py             # Google Gemini API integration for AI image generation
│   ├── image.py              # Image processing (resize, crop, overlay)
│   ├── minesweeper.py        # Minesweeper game logic
│   ├── rtb.py                # Ride the Bus game logic
│   ├── miniapp.py            # Mini app utilities (token encoding)
│   ├── logging_utils.py      # Logging configuration
│   └── services/             # Business logic layer (ALL DB operations go through here)
│       ├── card_service.py          # Card CRUD, claiming, locking, ownership
│       ├── aspect_service.py        # Aspect catalog, burn, lock, recycle, equip
│       ├── user_service.py          # User management, chat enrollment
│       ├── spin_service.py          # Spin balances, daily bonus, megaspin tracking
│       ├── claim_service.py         # Claim point balances
│       ├── rolled_card_service.py   # Rolled card state tracking (rerolls)
│       ├── rolled_aspect_service.py # Rolled aspect state tracking
│       ├── character_service.py     # Custom chat characters
│       ├── set_service.py           # Season/set management
│       ├── event_service.py         # Event logging with observer pattern
│       ├── achievement_service.py   # Achievement granting/checking
│       ├── trade_service.py         # Card and aspect trades
│       ├── rtb_service.py           # Ride the Bus game state
│       ├── aspect_count_service.py  # Aspect definition frequency per chat/season
│       ├── thread_service.py        # Thread ID storage for topic-based chats
│       └── admin_auth_service.py    # Admin JWT + OTP authentication
├── settings/
│   └── constants.py          # Loads config.json + env vars; rarity helpers, UI strings
├── data/                     # Game assets (card images, templates, slot assets, minesweeper assets)
├── tools/                    # Admin/maintenance scripts (backfills, exports, seed data)
└── alembic/                  # Database migration versions
```

### Frontend (`miniapp/`)
```
miniapp/src/
├── App.tsx                   # Route switcher based on useAppRouter
├── main.tsx                  # React root
├── pages/
│   ├── LandingPage.tsx       # Public landing page (no Telegram context)
│   ├── HubPage.tsx           # Main collection hub (5 tabs: Profile, Collection, Aspects, Casino, All Cards)
│   ├── SingleCardPage.tsx    # Fullscreen single card display
│   └── admin/               # Admin dashboard (login, management, set detail)
├── components/
│   ├── cards/               # Card, CardGrid (virtualized), CardModal, FilterSortControls, MiniCard
│   ├── aspects/             # AspectGrid (virtualized), AspectModal, MiniAspect
│   ├── casino/              # Casino catalog + game UIs
│   │   ├── slots/           # 3-reel slot machine with rarity wheel
│   │   ├── minesweeper/     # 3×3 grid game
│   │   └── rtb/             # Ride the Bus card guessing game
│   ├── tabs/                # ProfileTab, CollectionTab, AspectsTab, CasinoTab, AllCardsTab
│   ├── profile/             # ProfileView, Achievement badge
│   ├── common/              # BottomNav, ActionPanel, AnimatedImage, badges, dialogs
│   └── dialogs/             # BurnConfirmDialog, LockConfirmDialog
├── hooks/                   # ~21 custom hooks (useAppRouter, useCards, useSlots, useOrientation, etc.)
├── services/
│   └── api.ts               # ApiService class — all backend communication (static methods)
├── stores/                  # Zustand stores (useSlotsStore for animation state, useAdminStore for auth)
├── lib/                     # Image caching (4 layers: memory → IndexedDB → API)
├── types/
│   └── index.ts             # All TypeScript interfaces (CardData, AspectData, game types, etc.)
├── utils/                   # Animations (burn, rarity wheel, slot math, RTB), rarity styles, Telegram utils
└── assets/                  # Static images (landing page, casino covers)
```

### Top-Level Directories
```
├── cards/       # (empty placeholder)
├── casino/      # Placeholder subdirs: minesweeper/, rtb/, slots/
├── common/      # (empty placeholder)
├── dialogs/     # (empty placeholder)
├── profile/     # (empty placeholder)
├── tools/
│   └── process_achievement_icon.py  # Achievement icon processing utility
└── .github/
    ├── copilot-instructions.md      # This file
    └── AspectsUpdate.plan.md        # Gacha 2.0 migration plan (historical reference)
```

---

## Database Models (~24 tables)

### Core Models
| Model | Purpose |
|-------|---------|
| **CardModel** | Cards with base_name, rarity, owner, aspect_count, locked status, file_id, description; relationships to image and equipped aspects |
| **CardImageModel** | Card image (bytea) + thumbnail (bytea), linked 1:1 to CardModel |
| **UserModel** | Telegram user (user_id, username, display_name, profile_image, slot_icon) |
| **ChatModel** | User↔chat enrollment (composite PK: user_id + chat_id) |
| **ClaimModel** | Claim point balance per user per chat |
| **UserRollModel** | Roll rate limiting (last_roll_timestamp per user per chat) |

### Aspect System (Gacha 2.0)
| Model | Purpose |
|-------|---------|
| **AspectDefinitionModel** | Aspect catalog entries (name, rarity, set_id, season_id) |
| **OwnedAspectModel** | User-owned aspect instances (with optional custom name, rarity, locked, file_id) |
| **AspectImageModel** | Aspect sphere images (bytea) + thumbnails |
| **CardAspectModel** | Junction table: equipped aspects on cards (card_id, aspect_id, order 1-5) |
| **RolledAspectModel** | Rolled aspect tracking (reroll state) |
| **AspectCountModel** | Aspect definition frequency per chat/season |

### Games
| Model | Purpose |
|-------|---------|
| **SpinsModel** | Spin balance + login streak per user per chat |
| **MegaspinsModel** | Megaspin countdown tracking |
| **MinesweeperGameModel** | Active minesweeper game state (mine_positions JSONB, moves, status) |
| **RideTheBusGameModel** | Active RTB game state (bet_amount, card_ids JSONB, current_position, multiplier, status) |

### Infrastructure
| Model | Purpose |
|-------|---------|
| **RolledCardModel** | Rolled card tracking (reroll state) |
| **CharacterModel** | Custom chat characters (name, image, slot_icon) |
| **SetModel** | Card/aspect sets within seasons (name, source, description, active flag) |
| **ThreadModel** | Chat thread IDs for topic-based messaging |
| **EventModel** | Telemetry (event_type, outcome, user_id, chat_id, payload JSONB) |
| **AchievementModel** | Achievement definitions (name, description, icon) |
| **UserAchievementModel** | User achievement progress (unlocked_at) |
| **AdminUserModel** | Admin dashboard users (username, password_hash, OTP) |

---

## Design Principles

### Backend Organization
- **Handlers** (`bot/handlers/`): Telegram command handlers — thin layer that delegates to services
- **API Routers** (`bot/api/routers/`): FastAPI endpoints — organized by domain, delegates to services
- **Services** (`bot/utils/services/`): **All business logic lives here**; handlers/routers never do raw DB queries
- **Models** (`bot/utils/models.py`): SQLAlchemy ORM models with PostgreSQL-native types (JSONB, bytea, etc.)
- **Schemas** (`bot/utils/schemas.py`): Pydantic models for API request/response validation

### Handler Decorators (`bot/utils/decorators.py`)
Bot commands use decorators for auth/validation:
- `@verify_user` — user must be registered (via `/start`)
- `@verify_user_in_chat` — user must be enrolled in the current chat
- `@verify_admin` — user must be the configured admin
- `@prevent_concurrency(bot_data_key, cross_user=False)` — prevents race conditions on user actions via composite locking keys

### API Authentication
- **Mini App**: `Authorization: tma <initData>` header validated via Telegram's HMAC-SHA256 WebApp spec
- **Admin Dashboard**: JWT tokens issued after OTP verification via `admin_auth_service`

### Mini App Routing
The Mini App is launched with a `start_param` payload parsed by `useAppRouter`:
- `c-<cardId>` → Single card view
- `u-<userId>` → User collection
- `uc-<userId>-<chatId>` → Chat-scoped collection
- `casino-<chatId>` → Casino catalog
- `/admin` path → Admin dashboard

### Event System (`bot/utils/events.py`, `bot/utils/achievements.py`)
- **EventType** enum: ROLL, REROLL, CLAIM, TRADE, LOCK, BURN, REFRESH, RECYCLE, CREATE, SPIN, MEGASPIN, MINESWEEPER, RTB, DAILY_BONUS, EQUIP
- Each event type has its own outcome enum (e.g., ClaimOutcome: SUCCESS, ALREADY_OWNED, TAKEN, INSUFFICIENT, ERROR)
- Events are logged to the EventModel table and notify observers via `event_service.subscribe()`
- Achievement system uses observer pattern: event → check conditions → grant achievement if met
- All v1 achievements were cleared during Gacha 2.0 migration; infrastructure is preserved for future achievements

### Image Storage & Caching
- **Backend**: Card/aspect images stored as `bytea` in separate image tables; thumbnails auto-generated at 1/4 scale
- **Frontend**: 4-layer cache system: Memory Map → IndexedDB (30MB LRU) → API request
- **Virtualized rendering**: `@tanstack/react-virtual` for efficient grid display of large collections

### Frontend State Management
- **Zustand** stores for slot machine animation state and admin auth
- **Custom hooks** (~21) for data fetching, filtering, orientation tracking, gestures
- **Framer Motion** for card animations (RTB flip/move, transitions)
- **Device orientation** tracking via Telegram TWA SDK for 3D card tilt effects

---

## Bot Commands Reference

| Command | Handler | Description |
|---------|---------|-------------|
| `/start` | user.py | Register user |
| `/profile` | user.py | View/upload profile |
| `/delete` | user.py | Remove character |
| `/enroll` | user.py | Join current chat |
| `/unenroll` | user.py | Leave current chat |
| `/roll` | rolling.py | Roll a card or aspect |
| `/refresh` | cards.py | Refresh card modifiers/art |
| `/equip` | cards.py | Equip aspects onto cards |
| `/burn` | aspects.py | Burn aspect for spins |
| `/lock` | aspects.py | Lock/unlock aspect |
| `/recycle` | aspects.py | Upgrade aspects (3-4 → next tier) |
| `/create` | aspects.py | Forge unique aspect (5 Legendaries) |
| `/casino` | collection.py | View spin balance / open casino |
| `/balance` | collection.py | View claim points |
| `/collection` | collection.py | Browse card collection |
| `/stats` | collection.py | View user statistics |
| `/trade` | trade.py | Initiate card or aspect trade |
| `/spins` | admin.py | Add spins to user (admin) |
| `/reload` | admin.py | Reload bot config (admin) |
| `/set_thread` | admin.py | Set chat thread (admin) |

---

## Configuration

### Environment Variables (`.env`)
- `DATABASE_URL` — PostgreSQL connection string
- `TELEGRAM_AUTH_TOKEN` / debug token — Bot API tokens
- `GOOGLE_API_KEY` — Gemini API key
- `IMAGE_GEN_MODEL` — Gemini model name
- `BOT_ADMIN` — Admin username
- `CURRENT_SEASON` — Active season ID
- `SHADOW_STAGGERED_USERNAMES` — Users with artificial concurrency delays
- Mini App URLs, API base URLs, etc.

### Game Constants (`bot/config.json`)
All tunable game values including:
- Rarity weights, claim costs, spin rewards, lock costs
- Slot win chances (card: 2.25%, aspect: 4%, claim: 3.5%)
- Minesweeper mine count (2)
- RTB bet range (10–50), multiplier progression, cooldown (9h)
- Daily bonus progression (10→15→20→25→30→35→40 spins over 7-day streak)
- Megaspin threshold (100 spins)

---

## Development

### Running Locally
```bash
# Bot with debug mode (uses test bot token + api.telegram.org)
python bot/bot.py --debug

# API server
uvicorn bot.api.server:app --reload

# Mini App dev server
cd miniapp && npm run dev
```

### Database Changes
1. Modify models in `bot/utils/models.py`
2. Create Alembic migration: `cd bot && alembic revision -m "description"`
3. Migrations auto-run on startup via `database.py`

### Admin Dashboard
- Accessible at `/admin` path in the Mini App
- Login via OTP sent to admin's Telegram, exchanged for JWT
- Manages: seasons, sets, aspect definitions (CRUD + bulk operations)

---

## Key Conventions

- **Never bypass the service layer** — all DB operations go through `bot/utils/services/`
- **Use existing decorators** — don't reinvent auth/validation in handlers
- **Extend the ApiService class** — don't scatter fetch calls in frontend components; all backend calls go through `miniapp/src/services/api.ts`
- **Use typed events** — use the EventType and outcome enums when logging actions via `event_service.log()`
- **Token encoding** — mini app launch params must use the established payload format (`c-`, `u-`, `uc-`, `casino-`)
- **PostgreSQL-native types** — use JSONB for structured data, bytea for binary, DateTime(timezone=True) for timestamps
- **Image storage pattern** — separate image tables (CardImageModel, AspectImageModel) with bytea columns for full images + thumbnails
- **Virtual scrolling** — use `@tanstack/react-virtual` for any grid that may contain many items
- **Keep this file up to date** — after any structural change, new feature, or refactor, update this `copilot-instructions.md` to reflect the current project state
