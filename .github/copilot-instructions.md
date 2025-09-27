# GitHub Copilot – project guide

- Stack: Python Telegram bot + FastAPI (`bot/`) backed by SQLite, and a React/Vite mini-app (`miniapp/`) launched inside Telegram.
- Main bot entrypoint `bot/bot.py` wires commands, rolling, recycling, and sets the FastAPI app’s `set_bot_token`; respect decorators in `utils/decorators.py` when adding commands.
- Web API lives in `bot/api/server.py`; every handler validates Telegram `initData` from the `Authorization` header (`tma <payload>`). Reuse helper functions instead of custom validation.
- Tokens sent to the mini-app must be encoded via `bot/utils/miniapp.py`; only `c-<cardId>`, `u-<userId>`, and `uc-<userId>-<chatId>` payloads are supported after the `tg1_` base64 wrapper.
- Database access is centralized in `bot/utils/database.py`; it auto-runs Alembic migrations on startup. For schema changes add an Alembic revision under `bot/alembic/versions/`.
- Images are cached in SQLite (`image_b64` + `image_thumb_b64`) and thumb generation happens inside `add_card`; prefer using those helpers instead of bypassing them.
- The mini-app bootstraps through `miniapp/src/utils/telegram.ts`; it decodes `start_param` tokens and never falls back to other sources. Keep new payload types consistent with this parser.
- `miniapp/src/hooks/useCards.ts` initializes Telegram context, fetches the user collection through `ApiService.fetchUserCards`, and flips to single-card mode if the token requested `c-...`.
- Sharing a card calls `ApiService.shareCard` → `/cards/share`; the backend checks the auth user matches the payload and posts a `startapp` link with `encode_single_card_token`.
- Trade flows rely on the `chat_id` attached to cards; avoid reintroducing GROUP_CHAT_ID fallbacks except where explicitly documented (only the trade endpoint still has one for legacy reasons).
- `miniapp/src/App.tsx` orchestrates views (current/all/trade) and passes share handlers down to `Card` and `CardModal`; keep state updates memoized to avoid re-renders.
- Networking helpers live in `miniapp/src/services/api.ts`; they automatically add the `tma` header. Extend this class for new endpoints rather than scattering `fetch` calls.
- Cached images are stored via `miniapp/src/lib/imageCache.ts`; prefer fetching through that utility so repeated cards reuse data.
- Front-end styling lives in `App.css` plus per-component CSS; share button styles are under `.card-share-button`. Stay responsive—this runs inside the Telegram webview.
- Environment variables: set `TELEGRAM_AUTH_TOKEN` (and `DEBUG_TELEGRAM_AUTH_TOKEN`), `MINIAPP_URL`/`DEBUG_MINIAPP_URL`, and `GROUP_CHAT_ID`. The mini-app uses `VITE_API_BASE_URL` at build time.
- Install backend deps with `pip install -r bot/requirements.txt`; run the API via `uvicorn bot.api.server:app` (or launch the Telegram bot which spawns it).
- Mini-app commands (`npm install`, `npm run dev|build|lint`) execute from `/miniapp`; Node ≥18 works but avoid downgrading the repo’s pinned TypeScript/Vite versions.
- After changing the schema or migrations, run `alembic -c bot/alembic.ini upgrade head` against your SQLite file to verify the upgrade path.
- Before shipping front-end changes run `npm run build`; for API or bot changes, execute a quick smoke by starting the bot with `--debug` plus a sample SQLite database.
- Tests are light: rely on targeted manual runs and ensure Telegram init data validation is exercised where new endpoints read headers.
- Keep token logging terse—`miniapp/src/utils/telegram.ts` already emits payload decisions; add new logs at `info` level only if they help operators debug production.
- The `/tools/backfill_user_profiles.py` script updates avatars after schema changes; re-run it if you add new profile fields.
- When adding images or assets, place raw inputs under `data/` and generated cards under `data/cards/`; automation scripts assume that layout.
- Deployments: the mini-app ships via `miniapp/deploy.sh`, and the bot reads `.env.production`; update both when you introduce new environment knobs.
- Prefer incremental improvements (more caching, better error surfaces) once feature work is complete; log follow-up ideas in upcoming PR descriptions.

DO NOT BUILD THE APP / RUN TESTS / EXECUTE ANY COMMANDS UNLESS EXPLICITLY ASKED TO IN THE PROMPT.