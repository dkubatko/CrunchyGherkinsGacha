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
- **Slots**: Spin 3 reels to win cards or aspects; symbols are user avatars, character icons, claim point icons, and **aspect set icons**. Each aspect set has a generated slot icon reflecting its theme. When an aspect is won, the server pre-picks the exact set + aspect definition and shows the set's icon on the winning reels. Megaspins (guaranteed win) occur every ~100 regular spins
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

### Data Flow (3-Tier: Handler → Manager → Repository)
```
Telegram Chat                    Mini App (WebView)        Admin Dashboard
     │                                  │                        │
     ▼                                  ▼                        ▼
Bot Handlers ──────────────────► FastAPI Endpoints ◄──── Admin Routers
     │                                  │                        │
     └──────────► Manager Layer ◄───────┘────────────────────────┘
                  (business logic)
                       │
                       ▼
                Repository Layer
                 (data access)
                       │
                       ▼
             PostgreSQL Database
```

**Layer rules:**
- **Handlers** (`bot/handlers/`, `bot/api/routers/`): Thin entry points; orchestrate high-level flow via managers. May call repos directly for simple data retrieval.
- **Managers** (`bot/managers/`): Business logic, validation, game rules, cross-model orchestration. Call repos for data access.
- **Repositories** (`bot/repos/`): Pure data access — DB queries/mutations only. No business logic. Repos may import from other repos.

---

## Project Structure

### Backend (`bot/`)
```
bot/
├── bot.py                    # Entry point — init, create app, register handlers, run polling
├── config.py                 # Bot startup config, initializes utilities
├── config.json               # All tunable game constants (rarities, odds, rewards, cooldowns)
├── prompts/                  # Markdown prompt templates for Gemini image generation
│   ├── aspect_sphere.md      # Aspect sphere generation prompt
│   ├── base_card.md          # Base character card generation prompt
│   ├── equip_card.md         # Equip aspect onto existing card prompt
│   ├── refresh_card.md       # Full card regeneration with aspects prompt
│   ├── unique_aspect.md      # Addendum for Unique rarity aspects
│   ├── slot_icon.md          # Slot machine icon generation prompt (profile-based)
│   └── set_slot_icon.md      # Set slot icon generation prompt (text-to-image, theme-based)
├── core/
│   ├── application.py        # Factory: create_application() — debug vs production Telegram endpoints
│   └── handlers.py           # register_handlers() — wires all command & callback handlers
├── handlers/                 # Telegram command handlers (thin layer → services)
│   ├── user.py               # /start, /profile, /delete, /enroll, /unenroll, /notify
│   ├── rolling.py            # /roll (card/aspect), claim_/lock_/reroll_ callbacks
│   ├── cards.py              # /refresh, /equip + callbacks
│   ├── aspects.py            # /burn, /lock (aspect & card), /recycle, /create + callbacks
│   ├── collection.py         # /casino, /balance, /collection, /stats + navigation callbacks
│   ├── trade.py              # /trade, accept/reject callbacks for card & aspect trades
│   ├── admin.py              # /spins, /reload, /set_thread (admin-only)
│   ├── notifications.py      # Roll notification scheduling, DM sending, startup recovery
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
├── repos/                    # Repository layer — pure data access (DB queries only)
│   ├── card_repo.py              # Card CRUD, collection queries, ownership
│   ├── aspect_repo.py            # Aspect catalog, owned aspects, definition CRUD
│   ├── user_repo.py              # User management, chat enrollment, profiles
│   ├── spin_repo.py              # Spin balances, megaspin tracking
│   ├── claim_repo.py             # Claim point balances
│   ├── rolled_card_repo.py       # Rolled card state tracking (rerolls)
│   ├── rolled_aspect_repo.py     # Rolled aspect state tracking
│   ├── character_repo.py         # Custom chat characters
│   ├── set_repo.py               # Season/set management
│   ├── event_repo.py             # Event log queries
│   ├── achievement_repo.py       # Achievement data access
│   ├── rtb_repo.py               # Ride the Bus game record queries
│   ├── aspect_count_repo.py      # Aspect definition frequency per chat/season
│   ├── thread_repo.py            # Thread ID storage for topic-based chats
│   ├── admin_auth_repo.py        # Admin user lookups, OTP storage
│   ├── set_icon_repo.py          # Set slot icon CRUD (get, upsert, delete, bulk load)
│   ├── roll_repo.py              # Roll time tracking
│   ├── notification_repo.py      # Roll notification CRUD + deliverability checks
│   └── preferences_repo.py       # User preference CRUD (notify_rolls toggle)
├── managers/                 # Manager layer — business logic and orchestration
│   ├── card_manager.py           # Card claiming logic (row locks, point deduction)
│   ├── aspect_manager.py         # Aspect burn, recycle, equip, claim logic
│   ├── trade_manager.py          # Card and aspect trade orchestration
│   ├── spin_manager.py           # Daily bonus streaks, megaspin counter
│   ├── roll_manager.py           # Roll eligibility (cooldown checking)
│   ├── event_manager.py          # Event logging + observer pattern
│   ├── achievement_manager.py    # Achievement granting/syncing logic
│   ├── auth_manager.py           # Admin JWT + bcrypt authentication
│   ├── notification_manager.py   # Roll notification business logic (PTB-free)
│   └── casino/
│       └── rtb_manager.py        # Ride the Bus game state machine
├── utils/
│   ├── models.py             # All SQLAlchemy ORM models (~25 tables)
│   ├── schemas.py            # Pydantic DTOs — all repo functions return these (Card, OwnedAspect, User, etc.)
│   ├── database.py           # DB init + Alembic migration runner
│   ├── session.py            # SQLAlchemy engine/session factory, @with_session decorator, use_session() helper
│   ├── decorators.py         # @verify_user, @verify_user_in_chat, @verify_admin, @prevent_concurrency
│   ├── events.py             # EventType enums, outcome enums (ROLL, CLAIM, BURN, SPIN, etc.)
│   ├── achievements.py       # Achievement system (observer pattern on events)
│   ├── rolling.py            # Roll logic (determine rarity, generate cards/aspects)
│   ├── roll_manager.py       # Complex roll orchestration
│   ├── gemini.py             # Google Gemini API integration for AI image generation
│   ├── image.py              # Image processing (resize, crop, overlay)
│   ├── minesweeper.py        # Minesweeper game logic
│   ├── rtb.py                # Ride the Bus game logic (shim → managers.casino.rtb_manager)
│   ├── miniapp.py            # Mini app utilities (token encoding)
│   ├── logging_utils.py      # Logging configuration
│   ├── aspect_counts.py      # Aspect count event listener
│   └── slot_icon.py          # Slot icon generation utilities
├── settings/
│   └── constants.py          # Loads config.json + env vars; rarity helpers, UI strings
├── data/                     # Game assets (card images, templates, slot assets, minesweeper assets)
├── schema_baseline.sql       # pg_dump snapshot for fresh DB init (used by database.py)
├── Dockerfile                # Backend image (shared by bot + api, different CMD)
├── .dockerignore             # Excludes __pycache__, .env, legacy SQLite, etc.
├── tools/                    # Admin/maintenance scripts (backfills, exports, seed data)
│   └── backfill_set_icons.py     # One-time backfill of slot icons for existing sets
└── alembic/                  # Database migration versions
```

### Frontend (`miniapp/`)
```
miniapp/src/
├── App.tsx                   # Route switcher based on useAppRouter
├── main.tsx                  # React root
├── pages/
│   ├── LandingPage.tsx       # Public landing page (no Telegram context)
│   ├── HubPage.tsx           # Main collection hub (4 tabs: Profile, Collection, Casino, All)
│   ├── SingleCardPage.tsx    # Fullscreen single card display
│   ├── SingleAspectPage.tsx  # Fullscreen single aspect display
│   └── admin/               # Admin dashboard (login, management, set detail)
├── components/
│   ├── cards/               # Card, CardGrid (virtualized), CardModal, FilterSortControls, MiniCard
│   ├── aspects/             # AspectGrid (virtualized), AspectModal, MiniAspect, SingleAspectView
│   ├── casino/              # Casino catalog + game UIs
│   │   ├── slots/           # 3-reel slot machine with rarity wheel
│   │   ├── minesweeper/     # 3×3 grid game
│   │   └── rtb/             # Ride the Bus card guessing game
│   ├── tabs/                # ProfileTab, CollectionTab (Cards/Aspects sub-tabs), AspectsTab, CasinoTab, AllTab (Cards/Aspects sub-tabs)
│   ├── profile/             # ProfileView, Achievement badge
│   ├── common/              # BottomNav, ActionPanel, SubTabToggle, AnimatedImage, badges, dialogs
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
├── docker-compose.yml               # Docker Compose (prod profiles for Cloud SQL proxy)
├── deploy.sh                        # One-command deploy to GCP VM
├── .env.example              # Docker env var template (copy to .env)
├── tools/
│   └── process_achievement_icon.py  # Achievement icon processing utility
└── .github/
    ├── copilot-instructions.md      # This file
    └── AspectsUpdate.plan.md        # Gacha 2.0 migration plan (historical reference)
```

---

## Database Models (~25 tables)

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
| **SetIconModel** | Set slot icons (bytea) for casino reels; composite PK (set_id, season_id), FK to sets |

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
| **RollNotificationModel** | Scheduled roll-ready DM notifications (composite PK user_id+chat_id, notify_at, sent status) |
| **UserPreferencesModel** | Per-user preferences/settings (notify_rolls opt-out; extensible for future settings) |

---

## Design Principles

### Backend Organization (3-Tier: Handler → Manager → Repository)
- **Handlers** (`bot/handlers/`): Telegram command handlers — thin entry points that delegate to managers. May call repos directly for simple reads.
- **API Routers** (`bot/api/routers/`): FastAPI endpoints — organized by domain, delegate to managers. May call repos directly for simple reads.
- **Managers** (`bot/managers/`): Business logic, validation, game rules, cross-model orchestration. Call repos for all data access. **Never** make direct DB queries.
- **Repositories** (`bot/repos/`): Pure data access — DB queries/mutations only. **No business logic.** All repo functions return **Pydantic DTOs** (not ORM objects), converting inside the session boundary to prevent `DetachedInstanceError`. All repo functions accept an optional `session` keyword argument for transaction sharing.
- **Models** (`bot/utils/models.py`): SQLAlchemy ORM models with PostgreSQL-native types (JSONB, bytea, etc.) — used only inside repos.
- **Schemas** (`bot/utils/schemas.py`): Pydantic DTOs used throughout the app. Each schema has a `from_orm()` classmethod for ORM→DTO conversion (called inside repos only).

### Handler Decorators (`bot/utils/decorators.py`)
Bot commands use decorators for auth/validation:
- `@verify_user` — user must be registered (via `/start`)
- `@verify_user_in_chat` — user must be enrolled in the current chat (enrollment requires a complete profile: display name + photo)
- `@verify_admin` — user must be the configured admin
- `@prevent_concurrency(bot_data_key, cross_user=False)` — prevents race conditions on user actions via composite locking keys

### API Authentication
- **Mini App**: `Authorization: tma <initData>` header validated via Telegram's HMAC-SHA256 WebApp spec
- **Admin Dashboard**: JWT tokens issued after OTP verification via `admin_auth_service`

### Mini App Routing
The Mini App is launched with a `start_param` payload parsed by `useAppRouter`:
- `c-<cardId>` → Single card view
- `a-<aspectId>` → Single aspect view
- `u-<userId>` → User collection
- `uc-<userId>-<chatId>` → Chat-scoped collection
- `casino-<chatId>` → Casino catalog
- `/admin` path → Admin dashboard

### Event System (`bot/utils/events.py`, `bot/utils/achievements.py`)
- **EventType** enum: ROLL, REROLL, CLAIM, TRADE, LOCK, BURN, REFRESH, RECYCLE, CREATE, SPIN, MEGASPIN, MINESWEEPER, RTB, DAILY_BONUS, EQUIP
- Each event type has its own outcome enum (e.g., ClaimOutcome: SUCCESS, ALREADY_OWNED, TAKEN, INSUFFICIENT, ERROR)
- **SpinOutcome**: CARD_WIN, ASPECT_WIN, CLAIM_WIN, LOSS, NO_SPINS, ERROR
- **MegaspinOutcome**: SUCCESS (legacy), CARD_WIN, ASPECT_WIN, UNAVAILABLE, ERROR
- Events are logged to the EventModel table and notify observers via `event_manager.subscribe()`
- Achievement system uses observer pattern: event → check conditions → grant achievement if met
- **Aspect count tracking** (`bot/utils/aspect_counts.py`): Observer listens for aspect-creation events and increments per-chat, per-season usage counts in the `aspect_counts` table. The `ASPECT_CREATION_EVENTS` set defines which (event_type, outcome) tuples trigger counting. When logging new aspect-creation events, **always include `aspect_name` and `aspect_definition_id`** in the payload to ensure counts are tracked; the listener has a fallback to look up by `event.aspect_id` but explicit payload fields are preferred. Card-only events are ignored.
- All v1 achievements were cleared during Gacha 2.0 migration; infrastructure is preserved for future achievements

### Image Storage & Caching
- **Backend**: Card/aspect images stored as `bytea` in separate image tables; all images normalized to JPEG (quality 95) before storage; thumbnails auto-generated at 1/4 scale
- **Set slot icons**: Stored in `set_icons` table (bytea, 256×256 JPEG). Generated via text-to-image Gemini call using set name/description (no input portrait). Auto-generated on set creation; backfillable via `bot/tools/backfill_set_icons.py`
- **Frontend**: 4-layer cache system: Memory Map → IndexedDB (30MB LRU) → API request
- **Virtualized rendering**: `@tanstack/react-virtual` for efficient grid display of large collections

### Frontend State Management
- **Zustand** stores for slot machine animation state and admin auth
- **Custom hooks** (~21) for data fetching, filtering, orientation tracking, gestures
- **Framer Motion** for card animations (RTB flip/move, transitions)
- **Device orientation** tracking via Telegram TWA SDK for 3D card tilt effects

### Roll Notification System
- **Purpose**: DMs users when their 24-hour roll cooldown expires, with an inline button linking to the chat/thread
- **Architecture**: DB-backed notifications + PTB's `JobQueue` (APScheduler wrapper) in the bot process
- **Flow**: After each roll → atomically write `RollNotificationModel` + roll record in shared DB session → schedule `job_queue.run_once()` to fire at `roll_time + 24h`
- **Startup recovery**: `post_init` hook queries all unsent notifications — sends overdue ones immediately (rate-limited), re-schedules future ones in JobQueue
- **Deliverability check**: Before sending, verifies user is still enrolled in the chat, has not opted out (`UserPreferencesModel`), and the notification hasn't been superseded by a newer roll (stale job prevention via `notify_at` matching)
- **Opt-out**: Users toggle via `/notify` command; notifications are on by default; lazy row creation in `user_preferences` table
- **Deep links**: `https://t.me/c/{numeric_id}/{thread_id}` for topic chats; text-only DM for non-topic chats
- **Error handling**: `Forbidden` (user blocked bot) → mark sent; `RetryAfter` → sleep + retry; other errors → `mark_failed()` with attempt tracking

---

## Bot Commands Reference

| Command | Handler | Description |
|---------|---------|-------------|
| `/start` | user.py | Register user |
| `/profile` | user.py | View/upload profile |
| `/delete` | user.py | Remove character |
| `/enroll` | user.py | Join current chat (requires complete profile) |
| `/unenroll` | user.py | Leave current chat |
| `/help` | user.py | Show command reference |
| `/roll` | rolling.py | Roll a card or aspect |
| `/refresh` | cards.py | Refresh card modifiers/art |
| `/equip` | cards.py | Equip aspects onto cards |
| `/burn` | aspects.py | Burn aspect for spins |
| `/lock` | aspects.py | Lock/unlock aspect (`/lock <id>`) or card (`/lock card <id>`) |
| `/recycle` | aspects.py | Recycle aspects or cards (`/recycle [aspects\|cards] [rarity]`, 3-4 → next tier) |
| `/create` | aspects.py | Forge unique aspect (5 Legendaries) |
| `/casino` | collection.py | View spin balance / open casino |
| `/balance` | collection.py | View claim points |
| `/collection` | collection.py | Browse card collection |
| `/stats` | collection.py | View user statistics |
| `/trade` | trade.py | Initiate card or aspect trade |
| `/notify` | user.py | Toggle roll reminder DM notifications (on by default) |
| `/spins` | admin.py | Add spins to user (admin) |
| `/reload` | admin.py | Reload bot config (admin) |
| `/set_thread` | admin.py | Set chat thread (admin) |

---

## Configuration

### Environment Variables (`.env`)
- `DATABASE_URL` — PostgreSQL connection string
- `TELEGRAM_AUTH_TOKEN` / debug token — Bot API tokens
- `TELEGRAM_BOT_API_URL` — Local Telegram Bot API server URL (default: `http://localhost:8081`; Docker: `http://tg-bot-api:8081`)
- `CORS_ORIGINS` — Comma-separated allowed CORS origins (default: production + localhost)
- `GOOGLE_API_KEY` — Gemini API key
- `IMAGE_GEN_MODEL` — Gemini model name
- `BOT_ADMIN` — Admin username
- `CURRENT_SEASON` — Active season ID
- `SHADOW_STAGGERED_USERNAMES` — Users with artificial concurrency delays
- Mini App URLs, API base URLs, etc.
- See `.env.example` for the full list with descriptions

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

### Running Locally (without Docker)
```bash
# Bot with debug mode (uses test bot token + api.telegram.org)
python bot/bot.py --debug

# API server
uvicorn bot.api.server:app --reload

# Mini App dev server
cd miniapp && npm run dev
```

### Running with Docker
```bash
# Build and run entire stack (test locally before deploying)
docker compose up --build

# Production with Cloud SQL proxy
docker compose --profile prod up -d --build

# View logs
docker compose logs -f bot api

# Stop everything
docker compose down
```

### Docker Architecture
- **bot + api** share one Docker image (`bot/Dockerfile`), different `CMD`
- **frontend**: multi-stage build (Node → Nginx) via `miniapp/Dockerfile`, serves SPA and proxies `/api/` to api service
- **tg-bot-api** uses the official `aiogram/telegram-bot-api` image
- **cloud-sql-proxy** only runs with `--profile prod` (production Cloud SQL)
- Config: `.env` (from `.env.example`)
- Docker is for deployment/testing only; local dev runs natively without Docker

### Database Setup
- **Fresh DB detection**: `database.py` auto-detects empty databases, applies `schema_baseline.sql` (pg_dump snapshot), and stamps Alembic at head
- **Existing DB**: normal Alembic migrations run incrementally
- **New migrations**: modify `bot/utils/models.py`, then `cd bot && alembic revision -m "description"`
- Migrations auto-run on startup via `database.py`

### Admin Dashboard
- Accessible at `/admin` path in the Mini App
- Login via OTP sent to admin's Telegram, exchanged for JWT
- Manages: seasons, sets, aspect definitions (CRUD + bulk operations)

---

## Key Conventions

- **Follow the 3-tier layer rules** — Handlers → Managers → Repositories. Each layer only calls the layer below. Handlers may call repos directly for simple reads. Never bypass layers upward.
- **Repos return Pydantic DTOs** — All repo functions return Pydantic schemas (from `utils/schemas.py`), never raw ORM objects. The ORM→DTO conversion happens inside the repo's `@with_session` boundary to prevent `DetachedInstanceError`.
- **Session sharing for transactions** — All repo functions accept an optional `session=` keyword argument. Managers that need atomic multi-step operations open a session with `get_session(commit=True)` and pass it to each repo call. When a session is passed, the repo's `@with_session` decorator reuses it instead of creating a new one.
- **`FOR UPDATE` queries use `noload("*")`** — Queries with `.with_for_update()` must not use `joinedload` or `subqueryload` (PostgreSQL forbids `FOR UPDATE` with outer joins and `DISTINCT`). These queries only return scalar fields for validation; relationship data is not needed.
- **New code goes in repos/managers** — `bot/repos/` for data access, `bot/managers/` for business logic. The old `utils/services/` directory has been removed.
- **Use existing decorators** — don't reinvent auth/validation in handlers
- **Extend the ApiService class** — don't scatter fetch calls in frontend components; all backend calls go through `miniapp/src/services/api.ts`
- **Use typed events** — use the EventType and outcome enums when logging actions via `event_manager.log()`
- **Token encoding** — mini app launch params must use the established payload format (`c-`, `a-`, `u-`, `uc-`, `casino-`)
- **PostgreSQL-native types** — use JSONB for structured data, bytea for binary, DateTime(timezone=True) for timestamps
- **Image storage pattern** — separate image tables (CardImageModel, AspectImageModel, SetIconModel) with bytea columns for full JPEG images + JPEG thumbnails; Gemini output is always converted to JPEG via `ImageUtil.to_jpeg()` before any cropping/processing
- **Image generation config** — all Gemini calls include `image_size="1K"` for consistent resolution; aspect/slot/set-icon generation additionally specifies `aspect_ratio="1:1"`; card generation omits `aspect_ratio` (Gemini deduces 5:7 from base image). Set slot icons use text-to-image generation (no input portrait)
- **Prompt templates** — Gemini image generation prompts live in `bot/prompts/*.md` as Markdown files with `{placeholder}` parameters. Loaded at import time via `_load_prompt()` in `constants.py` and formatted with `.format()` in `gemini.py`. Edit prompts by modifying the `.md` files directly.
- **Virtual scrolling** — use `@tanstack/react-virtual` for any grid that may contain many items
- **Keep this file up to date** — after any structural change, new feature, or refactor, update this `copilot-instructions.md` to reflect the current project state
