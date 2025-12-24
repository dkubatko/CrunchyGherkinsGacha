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


class UserProfileResponse(BaseModel):
    """Full user profile response."""

    user_id: int
    username: str
    display_name: Optional[str] = None
    profile_imageb64: Optional[str] = None
    claim_balance: int
    spin_balance: int
    card_count: int


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
    next_refresh_time: Optional[str] = None
    megaspin: Optional[MegaspinInfo] = None


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
