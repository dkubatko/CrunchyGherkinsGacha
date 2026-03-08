# Gacha 2.0 — Aspect-Based Card Crafting Migration Plan

> A 10-step sequential migration that transforms the game from random modifier-based rolling to a user-driven card crafting system. Users roll base character cards (10%) and aspects (90%), then equip aspects onto base cards to create themed cards with custom names and AI-generated art.
>
> **The game will be taken offline for the duration of this migration.** Steps are ordered by logical dependency, not incremental deployment. Each step leaves the schema and code in a consistent, buildable state, but intermediate states are not guaranteed to be user-facing functional. The hard requirement is that existing data must not cause outages once the full migration is live.
>
> **Executor requirement:** Before implementing each step, the executor must evaluate the current state of the codebase and warn of any potential issues, conflicts, or deviations from the plan before committing to making the change. This includes verifying that prior steps were completed correctly, that no unexpected code drift has occurred, and that the planned changes are still compatible with the current state of the code.

---

## Product Changes Summary

### What Changes for Players

- **Rolling** now produces two types of items: **base character cards** (10% chance) and **aspects** (90% chance). Base cards depict a character with no theme applied. Aspects are collectible "snow globe sphere" items representing a thematic keyword (e.g., "Rainy" from the "Weather" set), each with unique AI-generated art.
- **Card crafting** is the new core loop. Players `/equip` an owned aspect onto a base card (or an already-modified card, up to 5 aspects). On first equip, the player names the card (e.g., "Sad Daniel"). Gemini generates a new card image blending the character with the applied aspects. Subsequent equips allow renaming and regenerate the art.
- **Aspects have rarities** (Common / Rare / Epic / Legendary) and can only be equipped on cards of equal or higher rarity — except **Unique aspects**, which can be equipped on any card.
- **Unique aspects** replace Unique cards. Players sacrifice 5 Legendary aspects via `/create` to forge a one-of-a-kind Unique aspect with a custom name and spectacular sphere art.
- **Burning & recycling** now apply to **aspects only**. Cards are permanent. Burning an aspect awards spins; recycling combines lower-rarity aspects into one of the next tier (3 Common→1 Rare, 3 Rare→1 Epic, 4 Epic→1 Legendary).
- **Trading** supports card↔card and aspect↔aspect swaps (no cross-type trades).
- **Slots** can now award aspects in addition to cards. Megaspins remain guaranteed wins.
- **Collection** in the Mini App gains a new "Aspects" tab showing unequipped aspects. Card detail views show equipped aspects.
- **Minesweeper** is disabled pending a future rework.
- **All achievements** are reset; a new achievement set will be introduced in a future update.

### What Stays the Same

- Overall app architecture (Bot + API + Mini App + SQLite/PostgreSQL).
- Claim points, spins, daily bonus, and the spin economy.
- RTB (Ride the Bus) casino game — operates on cards regardless of aspect status.
- Rolling cooldown, claim countdown, and the social claiming mechanic (any enrolled user can claim a roll).
- Card locking, card refreshing (`/refresh` regenerates art from scratch).
- Season scoping — all queries filter by current season.
- Admin dashboard for managing sets and aspect definitions (renamed from "modifiers" to "aspects").

---

## Confirmed Decisions

- **Seasons**: Increment to new season; old cards stay in DB filtered by season. No legacy marker needed — season filtering handles it.
- **Unique rarity**: Repurposed for user-created **Unique aspects** via `/create` (equipped on any rarity card).
- **Aspect images**: Every aspect instance has a **unique generated image**, stored in a dedicated `aspect_images` table (mirroring the `card_images` pattern).
- **Aspect consumption**: Equipped aspects leave the user's visible collection but persist as DB records linked to the card via a junction table.
- **Aspect definitions replace modifiers**: New aspect-related code uses an `aspect_definitions` catalog, not `modifiers`. The legacy modifier model/table may temporarily survive during migration as a compatibility artifact, but the end state has no modifier catalog.
- **Card `modifier` field repurposed**: The existing `modifier` column is kept only as a **legacy-named card prefix field** storing the user-chosen display prefix (e.g., `"Sad"`). It no longer refers to any aspect definition. The full display name is constructed by `title()` as `"{modifier} {base_name}"` (e.g., "Sad Daniel"). Base cards have `modifier = NULL`, causing `title()` to display just `base_name`.
- **Aspect naming**: Owned aspects need their own display-name storage so Unique/custom aspects do not need a catalog row. Each owned aspect therefore stores either an `aspect_definition_id` or a custom `name` override.
- **Equipped aspect source of truth**: `card_aspects` is the **only** source of truth for what aspects are equipped on a card. No duplicate `equipped_card_id` pointer exists on `owned_aspects`.
- **Equipped aspect ownership**: Equipped aspects always move with the card. Card trades atomically transfer ownership of the card **and all equipped aspects linked through `card_aspects`**.
- **Cards no longer belong to sets**: `cards.set_id` and `cards.modifier_id` become legacy metadata for pre-migration cards only. New card flows must treat them as irrelevant.
- **Economy**: Cards are non-burnable and non-recyclable. Only aspects can be burned and recycled.
- **Achievements**: All 15 existing achievements removed; fresh achievement system deferred to future iteration.
- **Roll split**: 10% base card / 90% aspect, configurable in `config.json`.
- **RTB**: Unchanged, operates on cards generically.
- **Minesweeper**: Disabled (code retained, unreachable).
- **Admin rename**: All admin endpoints and frontend references renamed from "modifiers" to "aspects".

---

## Step 1: Schema Foundation — New Tables & Columns

> Add all new DB structures without changing any existing behavior. The app continues working as-is after this step.

**New tables:**

- **`AspectDefinitionModel`** (`aspect_definitions`): `id` (PK auto), `set_id` (FK → sets.id within season), `season_id` (int), `name` (text), `rarity` (text), `created_at` (datetime). This replaces the old modifier catalog for all new aspect-related code. Step 1 seeds/backfills it from the existing modifier dataset.
- **`OwnedAspectModel`** (`owned_aspects`): `id` (PK auto), `aspect_definition_id` (nullable FK → aspect_definitions.id), `name` (nullable text override for custom/Unique aspects), `owner` (nullable username str), `user_id` (nullable bigint), `chat_id` (str), `season_id` (int), `rarity` (str), `locked` (bool, default False), `file_id` (nullable str, Telegram cache), `created_at` (datetime). Each row is a unique instance; images live in `aspect_images`. `owner` and `user_id` are nullable because aspect rolls are created without an owner and assigned on claim.
- **`AspectImageModel`** (`aspect_images`): `aspect_id` (PK, FK → owned_aspects.id), `image` (LargeBinary), `thumbnail` (LargeBinary), `image_updated_at` (nullable datetime). Mirrors the `card_images` table pattern — keeps metadata queries fast.
- **`CardAspectModel`** (`card_aspects`): `id` (PK auto), `card_id` (FK → cards.id), `aspect_id` (FK → owned_aspects.id), `order` (int, 1–5), `equipped_at` (datetime). Tracks which aspects are equipped on a card and in what order. This table is the sole source of truth for card↔aspect equipment state. `order` is assigned chronologically as `card.aspect_count + 1` at equip time; it is immutable after assignment and not user-controllable. Add uniqueness constraints for `aspect_id` and `(card_id, order)` plus a check enforcing `order BETWEEN 1 AND 5`.
- **`RolledAspectModel`** (`rolled_aspects`): Mirrors `RolledCardModel` but tracks aspect rolls. Columns: `roll_id` (PK auto), `original_aspect_id` (FK → owned_aspects.id, not null), `rerolled_aspect_id` (nullable FK → owned_aspects.id), `created_at` (datetime), `original_roller_id` (bigint), `rerolled` (bool, default False), `being_rerolled` (bool, default False), `attempted_by` (nullable text), `is_locked` (bool, default False), `original_rarity` (nullable text).

**Altered columns on existing tables:**

- **`CardModel`**:
  - Add `aspect_count` (Integer, default 0).
  - **Alter `modifier`**: change from `NOT NULL` to `nullable=True`. Base cards will have `modifier = NULL`; equipped cards store the user-chosen name prefix (e.g., `"Sad"`).
- **`CardModel` legacy metadata**:
  - `set_id` and `modifier_id` remain only for backward compatibility with pre-migration cards. New cards should leave them unset and new code must stop depending on them.
- **`EventModel`**:
  - Add `aspect_id` (nullable BigInteger). This parallels the existing `card_id` column and allows aspect-related events (`ROLL` with `type: aspect`, `EQUIP`, etc.) to be linked directly to the specific aspect without relying on `payload` JSONB parsing.
- **`RolledCardModel`**: No changes. Card rolls continue to use `RolledCardModel` as-is. Aspect rolls use the new `RolledAspectModel` instead.

**Pydantic schema updates:**

- **`Card` schema** (`bot/utils/schemas.py`): Change `modifier: str` → `modifier: Optional[str] = None`. Update `title()` to skip appending `self.modifier` when it is `None`, displaying only `base_name`. Add `aspect_count: int = 0` and `equipped_aspects: List[CardAspect] = []`.
- **`CardWithImage` schema**: Inherit updated `modifier` typing from `Card`.
- **`Event` schema**: Add `aspect_id: Optional[int] = None` field. Update `from_orm` to populate it.
- Add new schemas: `AspectDefinition`, `OwnedAspect`, `AspectImage`, `CardAspect`, `RolledAspect` to `bot/utils/schemas.py`. `OwnedAspect` resolves its display name from `name` override first, then `aspect_definition.name`.

**ORM model updates:**

- **`CardModel`** (`bot/utils/models.py`): Change `modifier: Mapped[str] = mapped_column(Text, nullable=False)` → `modifier: Mapped[Optional[str]] = mapped_column(Text, nullable=True)`. Update `title()` to handle `None` modifier. Add `equipped_aspects: Mapped[List["CardAspectModel"]] = relationship("CardAspectModel", back_populates="card", cascade="all, delete-orphan", order_by="CardAspectModel.order")` so that `joinedload(CardModel.equipped_aspects)` works naturally throughout the codebase.
- **`CardAspectModel`**: Add `card: Mapped["CardModel"] = relationship("CardModel", back_populates="equipped_aspects")` and `aspect: Mapped["OwnedAspectModel"] = relationship("OwnedAspectModel")` back-references.
- **`AspectDefinitionModel`**: New ORM model replacing legacy modifier semantics for all aspect-definition queries and admin flows.
- **`OwnedAspectModel`**: Add `aspect_definition`, `image: Mapped[Optional["AspectImageModel"]] = relationship("AspectImageModel", back_populates="aspect", uselist=False, cascade="all, delete-orphan")`, and `card_aspect_links: Mapped[List["CardAspectModel"]] = relationship("CardAspectModel")` relationships. Do **not** add `equipped_card_id`; equipped state is derived only from `card_aspect_links`.
- **`AspectImageModel`**: Add `aspect: Mapped["OwnedAspectModel"] = relationship("OwnedAspectModel", back_populates="image")` back-reference.
- **`EventModel`**: Add `aspect_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)` column and a corresponding index `idx_events_aspect_id`.

**Alembic migration** for all of the above (new tables, seed/backfill `aspect_definitions` from legacy modifier data, altered `cards.modifier` nullability, new `cards.aspect_count` column, and `card_aspects` integrity constraints).

---

## Step 2: Aspect Service Layer & Events

> Build the service layer for aspect CRUD, equip operations, and rolled aspect tracking. No handlers or UI changes yet — services are wired but uncalled.

**Create `aspect_service.py`** in `bot/utils/services/` with:

- `get_user_aspects(user_id, season_id)` — unequipped only (aspects with **no** `card_aspects` row).
- `get_aspect_by_id(id)` — returns `OwnedAspect` with image data.
- `add_owned_aspect(aspect_definition_id, chat_id, season_id, rarity, image, thumbnail, owner=None, user_id=None, name=None)` — creates `OwnedAspectModel` + `AspectImageModel`. `owner` and `user_id` are optional; left null for rolled aspects pending claim. `name` is used for Unique/custom aspects.
- `try_claim_aspect(aspect_id, user_id, username, chat_id)` — atomic claim using `SELECT ... FOR UPDATE` row-level lock **and** claim-point deduction in the same transaction. Returns failure if the aspect is already owned or the claimer lacks points.
- `lock_aspect(id, user_id)` — toggle lock.
- `get_aspects_for_card(card_id)` — returns ordered list of `CardAspect` records.
- `burn_aspect(id, user_id)` — validates ownership + not equipped + not locked, hard-deletes aspect and its image, awards spins based on rarity config, returns spin reward.
- `recycle_aspects(aspect_ids, user_id, target_rarity)` — validates all aspects are owned, unequipped, unlocked, same rarity (one tier below target); hard-deletes them and their images, returns nothing (caller generates new aspect). Mirrors card recycle: Common→Rare (3), Rare→Epic (3), Epic→Legendary (4).
- `equip_aspect_on_card(aspect_id, card_id, name_prefix)` — validates: ownership match, rarity compatibility (aspect rarity ≤ card rarity, Unique aspects exempt), `aspect_count < 5`, neither locked; row-locks both card and aspect, creates `CardAspectModel` with `order = card.aspect_count + 1`, increments card's `aspect_count`, and sets the card's legacy `modifier` field to `name_prefix` (the user-chosen prefix only, e.g., `"Sad"`). Equipping does NOT delete the aspect — it remains in the DB linked to the card through `card_aspects`.

**Fix card claiming in the same step:**

- Update `card_service.try_claim_card()` so card claims are also atomic: row-lock the card, validate claim balance, deduct claim points, and assign ownership inside a single transaction. Card and aspect claims must share the same transactional semantics.

**Create `rolled_aspect_service.py`** in `bot/utils/services/` mirroring `rolled_card_service.py`:

- `create_rolled_aspect(aspect_id, original_roller_id)` — creates `RolledAspectModel` entry.
- `get_rolled_aspect_by_roll_id(roll_id)` — returns `RolledAspect` schema.
- `get_rolled_aspect_by_aspect_id(aspect_id)` — lookup by original or rerolled aspect ID.
- `set_rolled_aspect_being_rerolled(roll_id, being_rerolled)` — toggle reroll-in-progress state.
- `set_rolled_aspect_rerolled(roll_id, new_aspect_id, original_rarity)` — mark as rerolled.
- `set_rolled_aspect_locked(roll_id, locked)` — toggle lock.
- `update_rolled_aspect_attempted_by(roll_id, username)` — append to attempted_by list.

**Extend `card_service.py`:**

- `get_card_with_aspects(card_id)` — returns card + ordered equipped aspects.
- Update `get_user_cards` to include `aspect_count` in results.

**Create `trade_service.py`** in `bot/utils/services/` and route all trade mutations through it:

- `trade_cards(card1_id, card2_id)` — swaps owners/user_ids of both cards and atomically transfers ownership of any equipped aspects attached through `card_aspects` so card ownership and equipped-aspect ownership never diverge.
- `trade_aspects(aspect1_id, aspect2_id)` — swaps owners/user_ids of two unequipped unlocked aspects.
- Bot handlers and API routes stop mutating ownership directly and delegate to this shared service.

**Events:**

- Add `EQUIP` event type to `bot/utils/events.py` with outcomes: `SUCCESS`, `FAILURE`.
- **No new `ASPECT_ROLL` event type.** Aspect rolls use the existing `ROLL` event type (`RollOutcome.SUCCESS` / `RollOutcome.ERROR`). A `type` discriminator field is included in the event `payload` to distinguish roll kinds: `{"type": "base_card", ...}` vs `{"type": "aspect", ...}`. All event consumers (analytics, listeners, future achievements) filter on `payload.type` when they need to distinguish roll kinds.
- Update `event_service.log()` to accept an optional `aspect_id` parameter, populating the new `EventModel.aspect_id` column for aspect-related events.
- Wire `EQUIP` event emission into `equip_aspect_on_card`.
- All events that operate on aspects (burn, recycle, trade, lock) use their existing event types (`BURN`, `RECYCLE`, `TRADE`, `LOCK`) with a `{"type": "aspect", ...}` discriminator in `payload` and the `aspect_id` column populated. This keeps the event type enum stable while allowing filtering by item type.
- Update roll/event consumers in the same phase so `ROLL.SUCCESS` with `payload.type == "aspect"` is never treated as card creation by listeners or achievements.

**Register** new services (`aspect_service`, `rolled_aspect_service`, `trade_service`) in `bot/utils/services/__init__.py`.

---

## Step 3: Aspect Image Generation & Card Generation Overhaul

> Rework the Gemini pipeline for three distinct generation modes. This step adds new functions alongside old ones — nothing is removed yet.

**New template asset:**

- Create `aspect_sphere.png` in `bot/data/card_templates/` — the snow globe sphere template.

**New prompts in `bot/settings/constants.py`:**

- **`ASPECT_GENERATION_PROMPT`**: Instructs Gemini to take the snow globe sphere template and the aspect name, stylizing the sphere thematically. Each generation produces a unique image. Includes `{aspect_name}` and `{set_context}` placeholders.
- **`EQUIP_GENERATION_PROMPT`**: Extension of the base card prompt. Takes the existing card image (replaces template + character photo) plus all equipped aspect sphere images. Structured with: "Applied aspects: [names + images already on the card]" and "Target aspect: [new aspect name + image to apply now]". Instructs Gemini to visually transform the card incorporating the new aspect while preserving character likeness and prior aspect themes.
- **`REFRESH_EQUIPPED_PROMPT`**: For `/refresh` on cards with aspects. Uses card template + character photo (from-scratch) + all equipped aspect sphere images + all aspect names. Generates a completely fresh image rather than iterating on the existing one.
- **`BASE_CARD_GENERATION_PROMPT`**: Simplified version of `CARD_GENERATION_PROMPT` with all modifier/modification references removed. Nameplate shows just the character name. Used for base card rolls and base card refreshes.

**New functions in `bot/utils/gemini.py`:**

- `generate_aspect_image(aspect_name, set_context=None)` — sends sphere template + `ASPECT_GENERATION_PROMPT` → returns processed sphere image.
- `generate_equipped_card_image(card_image, aspect_images_and_names, new_aspect_name, new_aspect_image, rarity, card_name)` — sends card image + all aspect sphere images + `EQUIP_GENERATION_PROMPT` → returns new card image.
- `generate_refresh_equipped_image(character_image, template_path, aspect_images_and_names, rarity, card_name)` — sends template + character photo + all aspect images + `REFRESH_EQUIPPED_PROMPT` → returns fresh card image.
- Modify existing `generate_image()`: add `no_modifier` parameter. When True, uses `BASE_CARD_GENERATION_PROMPT` with just character name on nameplate.

All new generation helpers use **aspect definition** metadata / aspect names for theme context; none of them depend on the legacy modifier catalog.

**Image utilities in `bot/utils/image.py`:**

- Aspect sphere images are **1:1 square** (unlike cards which are 5:7). Add `crop_to_square` post-processing in `generate_aspect_image()` — reuse the existing `ImageUtil.crop_to_square` already used for slot machine icons. Thumbnail generation uses the same 1/4 scale factor but preserves the 1:1 ratio.

---

## Step 4: Rolling Overhaul

> Transform `/roll` to produce either a base card (10%) or an aspect (90%). Both are claimable by any enrolled user.

**Config changes in `bot/config.json`:**

- Add `"roll_type_weights": {"base_card": 10, "aspect": 90}`.
- Aspect rarity weights reuse existing `roll_weight` values per rarity in `RARITIES`.

**Modify `generate_card_for_chat()`** in `bot/utils/rolling.py`:

- First determine roll type (base card vs aspect) using `roll_type_weights`.
- **Base card path**: skip modifier selection, call `generate_image(no_modifier=True)`, leave card's `modifier` as `NULL`. The card's `base_name` is the display name.
- **Aspect path**: select an aspect definition via `_choose_aspect_definition_for_rarity` weighted logic, call `generate_aspect_image()`, create `OwnedAspectModel` + `AspectImageModel` with `owner=None, user_id=None` (assigned on claim). Return aspect data instead of card data.

**Replace `RolledCardManager` with generalized `RollManager`** in `bot/utils/roll_manager.py` (or rename/extend `rolled_card.py`):

- Manages either a rolled card or rolled aspect based on roll type.
- Generates captions, keyboards, claim/lock/reroll state, and pre-claim countdown UI for both roll kinds.
- Uses `RolledCardModel` + card services for base-card rolls and `RolledAspectModel` + aspect services for aspect rolls.
- Renders sphere images/captions for aspects and card captions for cards.
- Reroll for aspects follows the same downgrade logic as card rerolls: rerolling a Rare aspect produces a Common aspect with a new random aspect definition and new sphere generation.

**Update roll handler** in `bot/handlers/rolling.py`:

- `handle_roll` determines roll type, then:
  - **Base card**: creates card via `card_service`, creates `RolledCardModel` via `rolled_card_service`, delegates to `RollManager` in card mode.
  - **Aspect**: creates aspect via `aspect_service.add_owned_aspect(owner=None)`, creates `RolledAspectModel` via `rolled_aspect_service`, delegates to `RollManager` in aspect mode.
- **Callback data prefixes must be distinct** to avoid ambiguity between card and aspect rolls. Card rolls use the existing `claim_{roll_id}`, `lock_{roll_id}`, `reroll_{roll_id}` prefixes. Aspect rolls use new prefixes: `aclaim_{roll_id}`, `alock_{roll_id}`, `areroll_{roll_id}`. Register separate callback handlers for each prefix set.
- `handle_claim` (cards): shared atomic card-claim flow, triggered by `^claim_` pattern.
- `handle_aspect_claim` (aspects): triggered by `^aclaim_` pattern, calls `aspect_service.try_claim_aspect(aspect_id, user_id, username, chat_id)` using the same transactional claim semantics as cards.
- Same prefix-splitting pattern applies to lock and reroll callbacks.

**Claim costs:** Aspect claiming uses the same `claim_cost` per rarity from the `RARITIES` config as card claiming. No new cost config needed.

**`file_id` caching:** When the bot sends an aspect sphere photo to chat and Telegram returns a `file_id`, store it on `OwnedAspectModel.file_id` — same pattern as card `file_id` population in `save_card_file_id_from_message`. The generalized `RollManager` handles this for both roll types.

**Log `ROLL` event** for both base card and aspect rolls. Include `{"type": "base_card", ...}` or `{"type": "aspect", ...}` in the event `payload` to distinguish roll kinds. For aspect rolls, also populate `aspect_id` on the event. For base card rolls, populate `card_id` as before.

**Claim countdown / reveal UI:** The countdown background task is updated in the same phase to use `RollManager`, not a card-only manager, so it can reveal buttons and captions for either roll type.

---

## Step 5: Equip System & Card Naming

> Implement the core crafting mechanic: equipping aspects onto base cards to create themed cards with user-chosen names and AI-generated art.

**Add `/equip` command** in `bot/handlers/cards.py`:

- Syntax: `/equip <aspect_id> <card_id> [name_prefix]`.
  - `aspect_id`: the owned aspect to equip.
  - `card_id`: the target card.
  - `name_prefix` (optional): the card name prefix. If omitted, defaults to the equipped aspect's display name (e.g., aspect "Rainy" → prefix becomes `"Rainy"`, display name `"Rainy Daniel"`). If provided, the user's custom string is used instead (e.g., `/equip 42 7 Sad` → display name `"Sad Daniel"`).
- Validates: ownership of both, rarity compatibility (aspect rarity ≤ card rarity; Unique aspects exempt), `aspect_count < 5`, neither item locked.
- **Name-prefix validation**: max 30 characters, no HTML/markdown special characters. The prefix (whether defaulted from aspect name or user-provided) is stored in the card's legacy `modifier` field. The full display name is always constructed by `title()` as `"{modifier} {base_name}"` — no parsing or suffix-matching logic needed.
- On subsequent equips (card already has a prefix), the new prefix argument (or aspect-name default) **replaces** the existing prefix. The user can explicitly keep the current name by passing it again.

**Equip execution as background task** (image generation takes time):

1. Show "Crafting..." message in chat.
2. Call `aspect_service.equip_aspect_on_card()` — this is a **single atomic transaction** that row-locks the card and aspect, creates the `CardAspectModel` junction row, increments the card's `aspect_count`, and sets the card's `modifier` field. If any validation fails, the entire transaction rolls back.
3. Call `generate_equipped_card_image()` from Step 3. This is a separate step outside the DB transaction (Gemini API call, can take 30+ seconds).
4. Update card image in `card_images` table, regenerate thumbnail, clear `file_id`. If image generation in step 3 fails, the card retains its old image but the aspect is still equipped and the modifier is updated — the card remains functional with stale art. Log a warning for manual resolution or prompt the user to `/refresh`.
5. Send result card photo to chat with updated caption (or a text-only notification if image generation failed).
6. Delete crafting message.

**Concurrency**: use `@prevent_concurrency` pattern; add `equipping` to in-progress operation sets.

**Edge cases**: locked card → block; locked aspect → block; card at 5 aspects → block; aspect rarity > card rarity (unless Unique) → block.

---

## Step 6: Disable Old Flows & Remove Achievements

> Clean break from v1 mechanics. Disable features that conflict with the new system.

**Disable minesweeper:**

- Remove handler registration from `bot/handlers/__init__.py`.
- Disable minesweeper API router in `bot/api/server.py`.
- Keep DB table and service code intact (future rework).

**Remove all achievements:**

- Delete all 15 achievement classes from `bot/utils/achievements.py`.
- Keep `AchievementSystem` infrastructure (observer, sync, grant) intact but with empty registry.
- Write Alembic migration to clear `achievements` and `user_achievements` tables.

**Disable card burn:**

- Remove `/burn` handler and `handle_burn` callback from `bot/handlers/cards.py`.
- Disable `POST /cards/burn` API endpoint in cards router.

**Disable card recycle:**

- Remove `/recycle` handler and `handle_recycle` callback from `bot/handlers/cards.py`.

**Repurpose `/burn` for aspects:**

- New `/burn` handler accepts aspect ID, calls `aspect_service.burn_aspect()`, awards spins per rarity config. Same confirmation flow (show aspect details → Yes/No → burn → report spins earned).

**Add `/recycle` for aspects:**

- New `/recycle` handler: syntax `/recycle <rarity>` (common/rare/epic). Mirrors old card recycle UX: shows how many aspects needed, selects random unlocked unequipped aspects of that rarity, confirmation prompt, burning animation, then generates one new aspect at the next rarity tier via `generate_aspect_image()`. Costs: Common→Rare (3), Rare→Epic (3), Epic→Legendary (4).

**Remove old modifier-on-roll path:**

- Clean `generate_card_for_chat()` in `bot/utils/rolling.py` — base card rolls never attach modifiers.
- **Rename & repurpose `_choose_modifier_for_rarity`** → `_choose_aspect_definition_for_rarity`. This function is still needed by the aspect roll path (it queries `aspect_definition_service.get_aspect_definitions_by_rarity()` and applies the weighted `1/(1+count)` selection logic). The rename clarifies its new role. Update all call sites in `rolling.py` and any other consumers.

**Disable minesweeper in Mini App:**

- Remove minesweeper from casino tab in `miniapp/src/pages/Hub.tsx`.

---

## Step 7: Revamp `/create` for Unique Aspects

> Repurpose the existing Unique creation flow: instead of creating Unique cards, users create Unique aspects.

**Modify `/create` command** in `bot/handlers/cards.py`:

- New syntax: `/create <AspectName>` (optionally with description on new line, max 300 chars).
- User sacrifices N Legendary **aspects** (not cards). Cost: `Unique.recycle_cost` (currently 5 Legendary aspects).
- Validates: user owns ≥ N unlocked, unequipped Legendary aspects.
- Duplicate check: no two Unique aspects with the same name in the same chat (reuse existing uniqueness check logic).

**Execution:**

1. Confirmation prompt: "Create Unique aspect '<Name>' by sacrificing 5 Legendary aspects?"
2. On confirm: burning animation (iterate through aspects with strikethrough, 1s each).
3. Call `generate_aspect_image()` with the user-chosen name and Unique-tier `creativeness_factor` (200). The sphere should be visually spectacular.
4. Create `OwnedAspectModel` with rarity "Unique", `name=<AspectName>`, `aspect_definition_id=NULL`, assigned to user immediately.
5. Send sphere photo to chat with "View in app" button.
6. Log `CREATE` event.

**Unique equip rules:** Unique aspects bypass the normal `aspect_rarity ≤ card_rarity` constraint — can be equipped on any card.

**Config:** ensure Unique rarity has `roll_weight: -1` (never rolled, only created).

---

## Step 8: Collection & API Overhaul

> Update the Mini App to display Cards and Aspects in separate tabs. Rename admin modifier endpoints to aspects.

**New `aspects.py` API router** in `bot/api/routers/`:

- `GET /aspects` — user's unequipped aspects (current season).
- `GET /aspects/{id}` — detail + base64 image.
- `POST /aspects/{id}/lock` — toggle lock.
- `POST /aspects/{id}/burn` — burn for spins.
- `GET /aspects/image/{id}` — full sphere PNG.
- `GET /aspects/thumbnail/{id}` — thumbnail sphere PNG.
- `GET /aspects/config` — burn rewards per rarity.

**API schemas** in `bot/api/schemas.py`:

- `AspectResponse`, `AspectDetailResponse`, `AspectListResponse`, `AspectConfigResponse`.

**Update card endpoints** in cards router:

- `GET /cards/{id}` returns `aspect_count` and list of equipped `CardAspect` objects (each with aspect name, rarity, set, thumbnail reference).
- `GET /cards/config` removes card burn rewards (cards non-burnable).

**Rename admin endpoints:**

- Rename the legacy modifier admin surface to aspect-definition admin: user-facing router `/admin/aspects`, but backed by `aspect_definitions` internally. Update all endpoint paths, function names, schema references, and frontend labels from "modifier" to "aspect" / "aspect definition" as appropriate.
- Rename `admin_sets` if needed (sets are still sets — they group aspects, so naming stays).
- Update `bot/api/server.py` router registration.

**Frontend — Mini App:**

- **Hub**: Add "Aspects" tab to `Hub.tsx` between Collection and Casino tabs.
- **AspectCollection component**: grid of owned (unequipped) aspect spheres, filterable by rarity and set. Tap → AspectDetail.
- **AspectDetail component**: sphere image, name, set, rarity. Actions: lock/unlock, burn, trade.
- **CardDetail update**: show list of equipped aspects below card image (thumbnails + names).
- **ApiService**: add aspect methods to `apiService.ts` — `getAspects()`, `getAspect(id)`, `lockAspect(id)`, `burnAspect(id)`, `getAspectImage(id)`, `getAspectThumbnail(id)`.
- **TypeScript types**: add `Aspect`, `AspectDetail`, `CardAspect` interfaces in `miniapp/src/types/`.
- **Admin pages**: rename modifier management pages/components to "Aspects" throughout.

**Update collection handler** in `bot/handlers/collection.py`:

- `/collection` shows card count + aspect count summary.
- "Show in chat" paginates cards only; aspects are Mini App–only.
- Card caption: show `modifier` as display name if set, otherwise just `base_name`.

---

## Step 9: Trading & Slots Overhaul

> Extend trading to support aspect-for-aspect trades and update slots to award aspects.

**Trading:**

- Update `/trade` handler in `bot/handlers/trade.py`: support two syntaxes:
  - `/trade <card_id> <card_id>` — **card↔card** (user-facing flow unchanged, but mutation routed through `trade_service`).
  - `/trade aspect <aspect_id> <aspect_id>` — **aspect↔aspect** (new flow).
- **Cross-type trades** (card-for-aspect or aspect-for-card) are explicitly rejected with a user-facing error message: `"Cross-type trades are not supported. You can only trade cards for cards or aspects for aspects."` This may be revisited in a future update.
- Route all trade mutations through `trade_service` from Step 2.
- `trade_cards(card1_id, card2_id)` swaps card ownership and atomically transfers all equipped aspects attached to each card.
- `trade_aspects(aspect1_id, aspect2_id)` swaps `owner` and `user_id` on both `OwnedAspectModel` records. Validates both unequipped and unlocked.
- Update confirmation UI: show sphere thumbnails + aspect names for aspect trades.
- Log `TRADE` event with appropriate payload distinguishing card vs aspect trades.

**Slots — aspect wins:**

- Add `"SLOT_ASPECT_WIN_CHANCE"` to `config.json` (e.g., `0.04`).
- In slots router `POST /slots/verify`: after card win check and before claim check, check aspect win chance. New outcome type `"aspect_win"` with rarity (weighted from `slots_weight` per rarity).
- **Update `SlotVerifyResponse`** in `bot/api/schemas.py`: add `win_type: Optional[str] = None` field with values `"card"`, `"aspect"`, or `None` (for losses/claim wins). This allows the frontend to distinguish win types and show the correct animation.
- Frontend handles new outcome with sphere-themed animation, keyed off `win_type`.

**Slots — aspect victory background task:**

- Create `process_slot_aspect_win` in `bot/api/background_tasks.py`:
  1. Select random aspect definition from active sets (source "all" or "slots").
  2. Determine rarity from `slots_weight`.
  3. Call `generate_aspect_image()`.
  4. Create `OwnedAspectModel` + `AspectImageModel`, assigned to winner.
  5. Send sphere photo to chat with notification.
  6. On failure: refund spins.

**Megaspins:** remain guaranteed **card** wins (premium reward). No aspect option.

**Update frontend** slot components to handle `"aspect_win"` result type.

---

## Step 10: Season Transition, Refresh Update & Final Cleanup

> Advance to the new season, update `/refresh`, remove all dead code.

**Season transition:**

- Write Alembic migration that documents the season increment. Update `CURRENT_SEASON` env var. All new rolls/aspects/cards are in the new season. Old-season items remain in DB, non-interactable by design.

**Update `/refresh`** in `bot/handlers/cards.py`:

- For cards with `modifier = NULL` (base cards, 0 aspects): regenerate with `generate_image(no_modifier=True)` using `BASE_CARD_GENERATION_PROMPT`. Existing refresh flow applies.
- For cards with aspects (1+ entries in `card_aspects`): call `generate_refresh_equipped_image()` — uses card template + character photo + all equipped aspect sphere images + all aspect names → generates from scratch. Same claim-point cost per rarity.

**Remove Unique from card context:**

- Unique rarity config remains for aspects (`spin_reward`, `creativeness_factor`, `recycle_cost`).
- Remove Unique from card roll weights, card slots weights, card display helpers.
- Remove old `/create` Unique card handler logic (replaced in Step 7).
- Update rarity display helpers in `bot/settings/constants.py`.

**Clean card display:**

- Cards show `"{modifier} {base_name}"` via `title()` if modifier is set (e.g., prefix `"Sad"` → display `"Sad Daniel"`), otherwise just `base_name` (e.g., `"Daniel"`).
- The existing `title()` concatenation pattern (`parts.append(self.modifier); parts.append(self.base_name)`) already handles this correctly once `modifier` is made nullable (Step 1). Remove any hardcoded `"{modifier} {base_name}"` string formatting in captions in `bot/settings/constants.py` and `bot/handlers/collection.py` that bypass `title()`.
- Frontend and API DTOs must also be updated so `modifier`/prefix is nullable everywhere and no client code blindly concatenates `modifier + base_name`.

**Remove card set semantics:**

- Stop exposing card `set_id`, `modifier_id`, or card-level `set_name` as meaningful fields for new cards.
- Any UI that needs set/theme context must derive it from the equipped aspect list, not from the card itself.
- Legacy pre-migration cards may still carry `set_id` / `modifier_id`, but all new code paths must treat them as optional historical metadata only.

**Rename modifier count system → aspect count system:**

- Rename table `modifier_counts` → `aspect_counts` (Alembic `ALTER TABLE ... RENAME TO`).
- Rename model `ModifierCountModel` → `AspectCountModel`.
- Rename column `modifier` (name string) → `aspect_name` (Alembic `ALTER COLUMN ... RENAME TO`). Rename `modifier_id` → `aspect_definition_id` so the count system references `aspect_definitions`, not legacy `modifiers`.
- Rename service file `modifier_count_service.py` → `aspect_count_service.py`. Update all imports and references in `bot/utils/services/__init__.py` and consumers.
- Update the event listener to subscribe to `ROLL` events and filter for `payload.type == "aspect"` instead of processing all `ROLL` events. The weighting logic (`1/(1+count)` favoring unseen aspects) stays identical.

**Remove legacy modifier catalog:**

- Delete the remaining legacy `modifiers` table/model/service once every consumer has moved to `aspect_definitions`.
- Rename any lingering `ModifierModel`, `Modifier` DTO, `modifier_service`, and related admin/frontend artifacts to their aspect-definition equivalents.
- Keep the card `modifier` column name only as a backward-compatibility field name for card display prefix; it is the one intentional exception.

**Clean prompts:**

- Active Gemini prompts: `BASE_CARD_GENERATION_PROMPT`, `ASPECT_GENERATION_PROMPT`, `EQUIP_GENERATION_PROMPT`, `REFRESH_EQUIPPED_PROMPT`.
- Remove or archive old `CARD_GENERATION_PROMPT` and `UNIQUE_ADDENDUM`.

**Frontend cleanup:**

- Remove minesweeper components/pages entirely.
- Remove Unique rarity from card UI (keep in aspect UI).
- Remove dead card burn/recycle UI.
- Update all type definitions.
- Rename any remaining "modifier" references to "aspect" in user-facing strings.

**Admin frontend cleanup:**

- Ensure all admin pages reference "aspects" not "modifiers".

**Final grep:**

- Search entire codebase for "modifier" references that should now say "aspect" in user-facing strings, API names, and component names.
- Verify no orphaned imports, dead service functions, or unreachable code paths remain.
- Ensure the new `EQUIP` event type flows through the observer system correctly, that both card and aspect claims are atomic, and that all events using `payload.type` discriminators (`"aspect"` vs `"base_card"`) are logged consistently.
- Verify all roll UI/background code uses the generalized `RollManager`, not card-only helpers.
