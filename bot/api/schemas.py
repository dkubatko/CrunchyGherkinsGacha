"""
API Request/Response schemas for the FastAPI server.

These are HTTP-specific contracts that define what the API accepts and returns.
They compose or reference the domain DTOs from utils.schemas but are separate
concerns from the database layer.
"""

from typing import Dict, List, Optional

from pydantic import BaseModel

from utils.schemas import Card


# =============================================================================
# USER SCHEMAS
# =============================================================================


class UserSummary(BaseModel):
    """Lightweight user summary for API responses."""

    user_id: int
    username: Optional[str] = None
    display_name: Optional[str] = None


class UserAchievementResponse(BaseModel):
    """Achievement data for API responses."""

    id: int
    name: str
    description: str
    icon_b64: Optional[str] = None
    unlocked_at: str  # ISO format datetime string


class UserProfileResponse(BaseModel):
    """Full user profile response."""

    user_id: int
    username: str
    display_name: Optional[str] = None
    profile_imageb64: Optional[str] = None
    claim_balance: int
    spin_balance: int
    card_count: int
    rarity_counts: Dict[str, int]
    achievements: List[UserAchievementResponse] = []


class UserCollectionResponse(BaseModel):
    """User's card collection response."""

    user: UserSummary
    cards: List[Card]


# =============================================================================
# CARD SCHEMAS
# =============================================================================


class CardImagesRequest(BaseModel):
    """Request for batch card images."""

    card_ids: List[int]


class CardImageResponse(BaseModel):
    """Response containing a single card's image."""

    card_id: int
    image_b64: str


class ShareCardRequest(BaseModel):
    """Request to share a card to chat."""

    card_id: int
    user_id: int


class LockCardRequest(BaseModel):
    """Request to lock or unlock a card."""

    card_id: int
    user_id: int
    chat_id: str
    lock: bool  # True to lock, False to unlock


class LockCardResponse(BaseModel):
    """Response after locking/unlocking a card."""

    success: bool
    locked: bool
    balance: int
    message: str
    lock_cost: int


class CardConfigResponse(BaseModel):
    """Configuration for card burn rewards and lock costs."""

    burn_rewards: Dict[str, int]
    lock_costs: Dict[str, int]


class BurnCardRequest(BaseModel):
    """Request to burn a card for spins."""

    card_id: int
    user_id: int
    chat_id: str


class BurnCardResponse(BaseModel):
    """Response after burning a card."""

    success: bool
    message: str
    spins_awarded: int
    new_spin_total: int


# =============================================================================
# SLOTS SCHEMAS
# =============================================================================


class SlotSymbolSummary(BaseModel):
    """Summary of a slot symbol for display."""

    id: int
    display_name: Optional[str] = None
    slot_iconb64: Optional[str] = None
    type: str  # "user", "character", or "claim"


class SlotSymbolInfo(BaseModel):
    """Minimal slot symbol info for verification."""

    id: int
    type: str  # "user", "character", or "claim"


class SlotsVictorySource(BaseModel):
    """Source of a slots victory (user or character)."""

    id: int
    type: str


class SlotsVictoryRequest(BaseModel):
    """Request to process a slots victory."""

    user_id: int
    chat_id: str
    rarity: str
    source: SlotsVictorySource
    is_megaspin: bool = False


class SlotsClaimWinRequest(BaseModel):
    """Request to process a claim point win from slots."""

    user_id: int
    chat_id: str
    amount: int


class SlotsClaimWinResponse(BaseModel):
    """Response after claim point win."""

    success: bool
    balance: int


class SpinsRequest(BaseModel):
    """Request for spin operations."""

    user_id: int
    chat_id: str


class MegaspinInfo(BaseModel):
    """Megaspin progress information."""

    spins_until_megaspin: int
    total_spins_required: int
    megaspin_available: bool


class SpinsResponse(BaseModel):
    """Response with spin balance info."""

    spins: int
    success: bool = True
    megaspin: Optional[MegaspinInfo] = None


class DailyBonusStatusResponse(BaseModel):
    """Response with daily bonus availability."""

    available: bool
    current_streak: int
    spins_to_grant: int
    max_display_streak: int = 7


class DailyBonusClaimResponse(BaseModel):
    """Response after claiming daily bonus."""

    success: bool
    spins_granted: int
    new_streak: int
    total_spins: int
    message: Optional[str] = None


class ClaimBalanceResponse(BaseModel):
    """Response with claim point balance."""

    balance: int
    user_id: int
    chat_id: str


class ConsumeSpinResponse(BaseModel):
    """Response after consuming a spin."""

    success: bool
    spins_remaining: Optional[int] = None
    message: Optional[str] = None
    megaspin: Optional[MegaspinInfo] = None


class SlotVerifyRequest(BaseModel):
    """Request to verify a slot spin result."""

    user_id: int
    chat_id: str
    random_number: int
    symbols: List[SlotSymbolInfo]


class SlotVerifyResponse(BaseModel):
    """Response with verified slot spin result."""

    is_win: bool
    slot_results: List[SlotSymbolInfo]
    rarity: Optional[str] = None


# =============================================================================
# MINESWEEPER SCHEMAS
# =============================================================================


class MinesweeperStartRequest(BaseModel):
    """Request to start a new minesweeper game."""

    user_id: int
    chat_id: str
    bet_card_id: int


class MinesweeperGameRequest(BaseModel):
    """Request for minesweeper game operations."""

    user_id: int
    chat_id: str


class MinesweeperStartResponse(BaseModel):
    """Response with minesweeper game state."""

    game_id: int
    status: str  # 'active', 'won', 'lost'
    bet_card_title: str  # Title of the bet card ("Rarity Modifier Name")
    card_rarity: str  # Rarity of the bet card
    revealed_cells: List[int]
    moves_count: int
    started_timestamp: str
    last_updated_timestamp: str
    reward_card_id: Optional[int] = None  # Only populated if status is 'won'
    mine_positions: Optional[List[int]] = None  # Only populated if status is 'won' or 'lost'
    claim_point_positions: Optional[List[int]] = (
        None  # Visible claim points (revealed or all if game over)
    )
    card_icon: Optional[str] = None  # Base64 slot icon of the game's selected source
    claim_point_icon: Optional[str] = None  # Base64 icon for claim points
    mine_icon: Optional[str] = None  # Base64 icon for mines
    next_refresh_time: Optional[str] = None  # When the next game can be started (if game is over)


class MinesweeperUpdateRequest(BaseModel):
    """Request to reveal a cell in minesweeper."""

    user_id: int
    game_id: int
    cell_index: int


class MinesweeperUpdateResponse(BaseModel):
    """Response after revealing a minesweeper cell."""

    revealed_cells: List[int]
    mine_positions: Optional[List[int]] = None  # Only populated if revealed cell is a mine
    claim_point_positions: Optional[List[int]] = (
        None  # Visible claim points (revealed or all if game over)
    )
    next_refresh_time: Optional[str] = (
        None  # When next game can be started (only if game just ended)
    )
    status: Optional[str] = None  # Game status: 'active', 'won', 'lost'
    bet_card_rarity: Optional[str] = None  # Rarity of the bet card (for alerts)
    source_display_name: Optional[str] = None  # Display name of the selected source (for alerts)
    claim_point_awarded: bool = False  # True if this reveal awarded a claim point


# =============================================================================
# RIDE THE BUS (RTB) SCHEMAS
# =============================================================================


class RTBCardInfo(BaseModel):
    """Card information for RTB game display."""

    card_id: int
    rarity: str
    title: str
    image_b64: Optional[str] = None  # Only provided for revealed cards


class RTBStartRequest(BaseModel):
    """Request to start a new RTB game."""

    user_id: int
    chat_id: str
    bet_amount: int  # 10-50 spins


class RTBGameResponse(BaseModel):
    """Response with RTB game state."""

    game_id: int
    status: str  # 'active', 'won', 'lost', 'cashed_out'
    bet_amount: int
    current_position: int  # 1-5 (how many cards revealed)
    current_multiplier: int  # Current multiplier (1, 2, 3, 5, or 10)
    next_multiplier: int  # Multiplier after next correct guess
    potential_payout: int  # Current bet * current multiplier
    cards: List[RTBCardInfo]  # Only revealed cards have full info
    started_timestamp: str
    last_updated_timestamp: str
    spins_balance: Optional[int] = None  # User's current spin balance
    cooldown_ends_at: Optional[str] = None  # ISO timestamp when cooldown ends (for won/cashed_out)


class RTBGuessRequest(BaseModel):
    """Request to make a guess in RTB."""

    user_id: int
    game_id: int
    guess: str  # 'higher', 'lower', or 'equal'


class RTBGuessResponse(BaseModel):
    """Response after making a guess."""

    correct: bool
    game: RTBGameResponse
    actual_comparison: str  # What the actual result was ('higher', 'lower', 'equal')
    message: str  # Human-readable result message


class RTBCashOutRequest(BaseModel):
    """Request to cash out of an RTB game."""

    user_id: int
    game_id: int


class RTBCashOutResponse(BaseModel):
    """Response after cashing out."""

    success: bool
    payout: int
    new_spin_total: int
    message: str
    game: RTBGameResponse


# =============================================================================
# ADMIN SCHEMAS
# =============================================================================


class AdminLoginRequest(BaseModel):
    """Credentials for admin dashboard login (step 1 of 2FA)."""

    username: str
    password: str


class AdminOTPRequest(BaseModel):
    """OTP verification for admin dashboard login (step 2 of 2FA)."""

    username: str
    code: str


class AdminTokenResponse(BaseModel):
    """JWT token returned after successful 2FA."""

    token: str


class AdminMeResponse(BaseModel):
    """Current admin session info."""

    admin_id: int
    username: str


class AdminSetResponse(BaseModel):
    """Set data returned by admin endpoints."""

    id: int
    season_id: int
    name: str
    source: str
    description: str
    active: bool
    modifier_count: int = 0


class AdminSetCreateRequest(BaseModel):
    """Request body to create a new set within a season."""

    name: str
    source: str = "all"
    description: str = ""
    active: bool = True


class AdminSetUpdateRequest(BaseModel):
    """Request body to update an existing set. Only provided fields are applied."""

    name: Optional[str] = None
    source: Optional[str] = None
    description: Optional[str] = None
    active: Optional[bool] = None


class AdminModifierResponse(BaseModel):
    """Modifier data returned by admin endpoints."""

    id: int
    name: str
    rarity: str
    set_id: int
    season_id: int
    created_at: str
    card_count: int = 0


class AdminModifierCreateRequest(BaseModel):
    """Request body to create a single modifier."""

    set_id: int
    season_id: int
    name: str
    rarity: str


class AdminModifierUpdateRequest(BaseModel):
    """Request body to update an existing modifier. Only provided fields are applied."""

    name: Optional[str] = None
    rarity: Optional[str] = None
    set_id: Optional[int] = None


class AdminBulkModifierItem(BaseModel):
    """A single item in a bulk modifier upsert."""

    set_id: int
    name: str
    rarity: str


class AdminBulkModifierRequest(BaseModel):
    """Request body for bulk modifier upsert."""

    season_id: int
    modifiers: List[AdminBulkModifierItem]


class AdminBulkModifierResponse(BaseModel):
    """Response from bulk modifier upsert."""

    upserted: int
