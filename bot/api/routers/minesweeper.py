"""
Minesweeper-related API endpoints.

This module contains all endpoints for minesweeper game operations including:
- Getting/creating minesweeper games
- Updating game state (revealing cells)
"""

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from api.background_tasks import (
    process_minesweeper_bet_notification,
    process_minesweeper_loss_background,
    process_minesweeper_victory_background,
)
from api.config import DEBUG_MODE, gemini_util
from api.dependencies import get_validated_user, verify_user_match
from api.helpers import ensure_utc, format_timestamp
from api.schemas import (
    MinesweeperStartRequest,
    MinesweeperStartResponse,
    MinesweeperUpdateRequest,
    MinesweeperUpdateResponse,
)
from utils import minesweeper, rolling
from utils.services import (
    card_service,
    claim_service,
    user_service,
    event_service,
)
from utils.events import EventType, MinesweeperOutcome

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/minesweeper", tags=["minesweeper"])


@router.get("/game", response_model=Optional[MinesweeperStartResponse])
async def minesweeper_game(
    user_id: int = Query(..., description="User ID"),
    chat_id: str = Query(..., description="Chat ID"),
    validated_user: Dict[str, Any] = Depends(get_validated_user),
):
    """
    Get the current minesweeper game for a user in a chat.

    - Returns the active game if one exists
    - Returns the most recent game if it was started within the last 24h (cooldown)
    - Returns None if no game exists or if the last game was completed more than 24h ago
    """
    # Verify the authenticated user matches the requested user_id
    await verify_user_match(user_id, validated_user)

    # Extract user data from validated data
    user_data: Dict[str, Any] = validated_user.get("user") or {}
    auth_user_id = user_data.get("id")

    # Get username
    username = user_data.get("username")
    if not username:
        username = await asyncio.to_thread(user_service.get_username_for_user_id, auth_user_id)
    if not username:
        logger.warning("Unable to resolve username for user_id %s", auth_user_id)
        raise HTTPException(status_code=400, detail="Username not found for user")

    # Validate chat_id
    chat_id = str(chat_id).strip()
    if not chat_id:
        logger.warning("Empty chat_id provided for minesweeper game")
        raise HTTPException(status_code=400, detail="chat_id is required")

    # Verify user is enrolled in the chat
    is_member = await asyncio.to_thread(user_service.is_user_in_chat, chat_id, user_id)
    if not is_member:
        logger.warning("User %s not enrolled in chat %s", user_id, chat_id)
        raise HTTPException(status_code=403, detail="User not enrolled in this chat")

    try:
        # Get existing game (does not create)
        game = await asyncio.to_thread(
            minesweeper.get_existing_game,
            user_id,
            chat_id,
        )

        # No game found or cooldown expired
        if not game:
            return None

        logger.info(
            "Minesweeper game %s fetched for user %s in chat %s (status: %s)",
            game.id,
            user_id,
            chat_id,
            game.status,
        )

        # Use stored bet_card_title and bet_card_rarity from game (preserves data even if card is deleted)
        bet_card_title = game.bet_card_title or "Unknown Card"
        card_rarity = game.bet_card_rarity or "Common"

        # Only include mine positions if game is over (won/lost)
        mine_positions = game.mine_positions if game.status in ("won", "lost") else None

        # Include claim point positions that have been revealed, or all if game is over
        if game.status in ("won", "lost"):
            visible_claim_points = game.claim_point_positions
        else:
            visible_claim_points = [
                pos for pos in game.claim_point_positions if pos in game.revealed_cells
            ]

        # Fetch the slot icon for the game's source (not the bet card's source)
        card_icon = None
        if game.source_type and game.source_id:
            card_icon = await asyncio.to_thread(
                minesweeper.get_source_icon, game.source_type, game.source_id
            )

        # Load minesweeper icons
        claim_point_icon, mine_icon = await asyncio.to_thread(minesweeper.get_minesweeper_icons)

        started_timestamp = ensure_utc(game.started_timestamp)
        last_updated_timestamp = ensure_utc(game.last_updated_timestamp)

        # Calculate next refresh time only if game is over
        next_refresh_time = None
        if game.status in ("won", "lost") and started_timestamp is not None:
            cooldown_seconds = 60 if DEBUG_MODE else 24 * 60 * 60
            next_refresh = started_timestamp + timedelta(seconds=cooldown_seconds)
            next_refresh_time = format_timestamp(next_refresh)

        return MinesweeperStartResponse(
            game_id=game.id,
            status=game.status,
            bet_card_title=bet_card_title,
            card_rarity=card_rarity,
            revealed_cells=game.revealed_cells,
            moves_count=game.moves_count,
            started_timestamp=format_timestamp(started_timestamp),
            last_updated_timestamp=format_timestamp(last_updated_timestamp),
            reward_card_id=game.reward_card_id,
            mine_positions=mine_positions,
            claim_point_positions=visible_claim_points,
            card_icon=card_icon,
            claim_point_icon=claim_point_icon,
            mine_icon=mine_icon,
            next_refresh_time=next_refresh_time,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error fetching minesweeper game: %s", e)
        raise HTTPException(status_code=500, detail="Failed to fetch game")


@router.post("/game/create", response_model=MinesweeperStartResponse)
async def minesweeper_create(
    request: MinesweeperStartRequest,
    validated_user: Dict[str, Any] = Depends(get_validated_user),
):
    """
    Create a new minesweeper game.

    - Validates that no active game exists
    - Validates that 24h cooldown has passed since last game
    - Creates a new game with the specified bet card
    - Generates random mine and claim point positions
    """
    # Verify the authenticated user matches the requested user_id
    await verify_user_match(request.user_id, validated_user)

    # Extract user data from validated data
    user_data: Dict[str, Any] = validated_user.get("user") or {}
    auth_user_id = user_data.get("id")

    # Get username
    username = user_data.get("username")
    if not username:
        username = await asyncio.to_thread(user_service.get_username_for_user_id, auth_user_id)
    if not username:
        logger.warning("Unable to resolve username for user_id %s", auth_user_id)
        raise HTTPException(status_code=400, detail="Username not found for user")

    # Validate chat_id
    chat_id = str(request.chat_id).strip()
    if not chat_id:
        logger.warning("Empty chat_id provided for minesweeper start")
        raise HTTPException(status_code=400, detail="chat_id is required")

    # Verify user is enrolled in the chat
    is_member = await asyncio.to_thread(user_service.is_user_in_chat, chat_id, request.user_id)
    if not is_member:
        logger.warning("User %s not enrolled in chat %s", request.user_id, chat_id)
        raise HTTPException(status_code=403, detail="User not enrolled in this chat")

    # Verify the bet card exists and is owned by the user
    card = await asyncio.to_thread(card_service.get_card, request.bet_card_id)
    if not card:
        logger.warning(
            "Minesweeper start requested with non-existent card_id: %s", request.bet_card_id
        )
        raise HTTPException(status_code=404, detail="Card not found")

    if card.owner != username:
        logger.warning(
            "User %s (%s) attempted to bet card %s owned by %s",
            username,
            auth_user_id,
            request.bet_card_id,
            card.owner,
        )
        raise HTTPException(status_code=403, detail="You do not own this card")

    if card.rarity.lower() == "unique":
        logger.warning(
            "User %s (%s) attempted to bet Unique card %s",
            username,
            auth_user_id,
            request.bet_card_id,
        )
        raise HTTPException(status_code=400, detail="Unique cards cannot be used in Minesweeper")

    # Verify card is from the same chat
    if card.chat_id != chat_id:
        logger.warning(
            "Card %s chat_id mismatch. Card chat: %s, Request chat: %s",
            request.bet_card_id,
            card.chat_id,
            chat_id,
        )
        raise HTTPException(status_code=400, detail="Card is not from this chat")

    try:
        # Check if a game already exists
        existing_game = await asyncio.to_thread(
            minesweeper.get_existing_game,
            request.user_id,
            chat_id,
        )

        if existing_game:
            # Active game exists
            if existing_game.status == "active":
                logger.warning(
                    "User %s attempted to create game while game %s is active",
                    request.user_id,
                    existing_game.id,
                )
                raise HTTPException(
                    status_code=400,
                    detail="You already have an active game. Finish it before starting a new one.",
                )

            # Cooldown not expired
            cooldown_seconds = 60 if DEBUG_MODE else 24 * 60 * 60
            existing_start = ensure_utc(existing_game.started_timestamp) or datetime.now(
                timezone.utc
            )
            time_since_start = datetime.now(timezone.utc) - existing_start
            if time_since_start.total_seconds() < cooldown_seconds:
                time_remaining_seconds = cooldown_seconds - time_since_start.total_seconds()

                if DEBUG_MODE:
                    # Show seconds for debug mode
                    seconds_remaining = int(time_remaining_seconds)
                    logger.warning(
                        "User %s attempted to create game during cooldown. %s seconds remaining",
                        request.user_id,
                        seconds_remaining,
                    )
                    raise HTTPException(
                        status_code=400,
                        detail=f"You must wait {seconds_remaining} more seconds before starting a new game.",
                    )
                else:
                    # Show hours for production mode
                    hours_remaining = time_remaining_seconds / 3600
                    logger.warning(
                        "User %s attempted to create game during cooldown. %s hours remaining",
                        request.user_id,
                        hours_remaining,
                    )
                    raise HTTPException(
                        status_code=400,
                        detail=f"You must wait {hours_remaining:.1f} more hours before starting a new game.",
                    )

        # Create new game with bet card title and rarity
        bet_card_title = card.title()
        bet_card_rarity = card.rarity
        game = await asyncio.to_thread(
            minesweeper.create_game,
            request.user_id,
            chat_id,
            request.bet_card_id,
            bet_card_title,
            bet_card_rarity,
        )

        if not game:
            logger.error("Failed to get or create minesweeper game for user %s", request.user_id)
            raise HTTPException(status_code=500, detail="Failed to start game")

        # Log game created
        event_service.log(
            EventType.MINESWEEPER,
            MinesweeperOutcome.CREATED,
            user_id=request.user_id,
            chat_id=chat_id,
            card_id=request.bet_card_id,
            game_id=game.id,
            bet_card_rarity=bet_card_rarity,
        )

        # Send bet notification to chat (fire-and-forget background task)
        asyncio.create_task(
            process_minesweeper_bet_notification(
                username=username,
                card_title=card.title(include_rarity=True),
                chat_id=chat_id,
            )
        )

        logger.info(
            "Minesweeper game %s started/resumed for user %s in chat %s with card %s (status: %s)",
            game.id,
            request.user_id,
            chat_id,
            request.bet_card_id,
            game.status,
        )

        # Only include mine positions if game is over (won/lost)
        # During active gameplay, client should not know where bombs are
        mine_positions = game.mine_positions if game.status in ("won", "lost") else None

        # Include claim point positions that have been revealed, or all if game is over
        if game.status in ("won", "lost"):
            # Game is over, show all claim points
            visible_claim_points = game.claim_point_positions
        else:
            # Game is active, only show revealed claim points
            visible_claim_points = [
                pos for pos in game.claim_point_positions if pos in game.revealed_cells
            ]

        # Fetch the slot icon for the game's source (not the bet card's source)
        card_icon = None
        if game.source_type and game.source_id:
            card_icon = await asyncio.to_thread(
                minesweeper.get_source_icon, game.source_type, game.source_id
            )

        # Load minesweeper icons
        claim_point_icon, mine_icon = await asyncio.to_thread(minesweeper.get_minesweeper_icons)

        started_timestamp = ensure_utc(game.started_timestamp)
        last_updated_timestamp = ensure_utc(game.last_updated_timestamp)

        # Calculate next refresh time only if game is over
        next_refresh_time = None
        if game.status in ("won", "lost") and started_timestamp is not None:
            cooldown_seconds = 60 if DEBUG_MODE else 24 * 60 * 60
            next_refresh = started_timestamp + timedelta(seconds=cooldown_seconds)
            next_refresh_time = format_timestamp(next_refresh)

        return MinesweeperStartResponse(
            game_id=game.id,
            status=game.status,
            bet_card_title=bet_card_title,
            card_rarity=bet_card_rarity,
            revealed_cells=game.revealed_cells,
            moves_count=game.moves_count,
            started_timestamp=format_timestamp(started_timestamp),
            last_updated_timestamp=format_timestamp(last_updated_timestamp),
            reward_card_id=game.reward_card_id,
            mine_positions=mine_positions,
            claim_point_positions=visible_claim_points,
            card_icon=card_icon,
            claim_point_icon=claim_point_icon,
            mine_icon=mine_icon,
            next_refresh_time=next_refresh_time,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error starting minesweeper game: %s", e)
        raise HTTPException(status_code=500, detail="Failed to start game")


@router.post("/game/update", response_model=MinesweeperUpdateResponse)
async def minesweeper_update(
    request: MinesweeperUpdateRequest,
    validated_user: Dict[str, Any] = Depends(get_validated_user),
):
    """
    Reveal a cell in the minesweeper game.

    - Validates that the cell hasn't been revealed yet
    - Updates game state (revealed_cells, moves_count)
    - Checks win/loss conditions:
      * Loss: Revealed cell contains a mine
      * Win: Revealed 3 safe cells
    - Returns whether the cell is a mine and updated game state
    """
    # Verify the authenticated user matches the requested user_id
    await verify_user_match(request.user_id, validated_user)

    # Extract user data from validated data
    user_data: Dict[str, Any] = validated_user.get("user") or {}
    auth_user_id = user_data.get("id")

    # Get username
    username = user_data.get("username")
    if not username:
        username = await asyncio.to_thread(user_service.get_username_for_user_id, auth_user_id)
    if not username:
        logger.warning("Unable to resolve username for user_id %s", auth_user_id)
        raise HTTPException(status_code=400, detail="Username not found for user")

    try:
        # Get the game to verify ownership and status
        game = await asyncio.to_thread(minesweeper.get_game_by_id, request.game_id)

        if not game:
            logger.warning(
                "Minesweeper update requested for non-existent game_id: %s", request.game_id
            )
            raise HTTPException(status_code=404, detail="Game not found")

        # Verify the game belongs to the requesting user
        if game.user_id != request.user_id:
            logger.warning(
                "User %s attempted to update game %s owned by user %s",
                request.user_id,
                request.game_id,
                game.user_id,
            )
            raise HTTPException(status_code=403, detail="You do not own this game")

        # Verify game is still active
        if game.status != "active":
            logger.warning(
                "User %s attempted to update completed game %s (status: %s)",
                request.user_id,
                request.game_id,
                game.status,
            )
            raise HTTPException(
                status_code=400, detail=f"Game is already completed with status: {game.status}"
            )

        # Get the bet card info for responses
        card = await asyncio.to_thread(card_service.get_card, game.bet_card_id)
        if not card:
            logger.error("Bet card %s not found for game %s", game.bet_card_id, request.game_id)
            raise HTTPException(status_code=500, detail="Game data inconsistent")

        # Get source display name
        source_display_name = None
        if game.source_type and game.source_id:
            try:
                source_profile = await asyncio.to_thread(
                    rolling.get_profile_for_source, game.source_type, game.source_id
                )
                source_display_name = source_profile.name
            except Exception as e:
                logger.warning(
                    "Failed to get source display name for %s:%s: %s",
                    game.source_type,
                    game.source_id,
                    e,
                )

        # Validate cell index
        if request.cell_index < 0 or request.cell_index >= 9:
            logger.warning(
                "User %s provided invalid cell_index %s for game %s",
                request.user_id,
                request.cell_index,
                request.game_id,
            )
            raise HTTPException(status_code=400, detail="Cell index must be between 0 and 8")

        # Check if cell was already revealed
        if request.cell_index in game.revealed_cells:
            logger.warning(
                "User %s attempted to reveal already revealed cell %s in game %s",
                request.user_id,
                request.cell_index,
                request.game_id,
            )
            raise HTTPException(status_code=400, detail="Cell has already been revealed")

        # Check if the cell has a mine BEFORE updating
        is_mine = request.cell_index in game.mine_positions

        # Check if the cell has a claim point BEFORE updating
        is_claim_point = request.cell_index in game.claim_point_positions
        claim_point_awarded = False

        # Award claim point if revealing a claim point cell
        if is_claim_point and request.cell_index not in game.revealed_cells:
            try:
                new_balance = await asyncio.to_thread(
                    claim_service.increment_claim_balance,
                    request.user_id,
                    game.chat_id,
                    1,
                )
                claim_point_awarded = True
                logger.info(
                    "User %s earned 1 claim point in minesweeper game %s. New balance: %s",
                    request.user_id,
                    request.game_id,
                    new_balance,
                )
            except Exception as e:
                logger.error(
                    "Failed to award claim point to user %s in game %s: %s",
                    request.user_id,
                    request.game_id,
                    e,
                )

        # Reveal the cell and update game state
        updated_game = await asyncio.to_thread(
            minesweeper.reveal_cell,
            request.game_id,
            request.cell_index,
        )

        if not updated_game:
            logger.error(
                "Failed to reveal cell %s in game %s",
                request.cell_index,
                request.game_id,
            )
            raise HTTPException(status_code=500, detail="Failed to update game")

        logger.info(
            "Minesweeper game %s: user %s revealed cell %s (mine=%s, new_status=%s)",
            request.game_id,
            request.user_id,
            request.cell_index,
            is_mine,
            updated_game.status,
        )

        if updated_game.status in ("won", "lost"):
            # Game is over, expose board metadata while keeping actual revealed history
            mine_positions = updated_game.mine_positions
            visible_claim_points = updated_game.claim_point_positions
        else:
            # Only include mine positions if the revealed cell was a mine
            mine_positions = updated_game.mine_positions if is_mine else None

            # Game is active, only show revealed claim points
            visible_claim_points = [
                pos
                for pos in updated_game.claim_point_positions
                if pos in updated_game.revealed_cells
            ]
        revealed_cells = updated_game.revealed_cells

        # Calculate next refresh time if game just ended
        next_refresh_time = None
        if updated_game.status in ("won", "lost"):
            started_timestamp = ensure_utc(updated_game.started_timestamp)
            if started_timestamp is not None:
                cooldown_seconds = 60 if DEBUG_MODE else 24 * 60 * 60
                next_refresh = started_timestamp + timedelta(seconds=cooldown_seconds)
                next_refresh_time = format_timestamp(next_refresh)

        # Spawn background tasks if game ended
        if updated_game.status == "won":
            # Calculate total claim points earned during the game
            claim_points_earned = len(
                set(updated_game.revealed_cells) & set(updated_game.claim_point_positions)
            )
            # Log win event
            event_service.log(
                EventType.MINESWEEPER,
                MinesweeperOutcome.WON,
                user_id=request.user_id,
                chat_id=game.chat_id,
                card_id=game.bet_card_id,
                game_id=request.game_id,
                cells_revealed=len(revealed_cells),
                claim_points_earned=claim_points_earned,
            )
            # Victory: generate new card for the player
            asyncio.create_task(
                process_minesweeper_victory_background(
                    username=username,
                    user_id=request.user_id,
                    chat_id=game.chat_id,
                    rarity=card.rarity,
                    source_type=game.source_type,
                    source_id=game.source_id,
                    display_name=source_display_name or "Unknown",
                    gemini_util_instance=gemini_util,
                )
            )
        elif updated_game.status == "lost":
            # Calculate total claim points earned during the game
            claim_points_earned = len(
                set(updated_game.revealed_cells) & set(updated_game.claim_point_positions)
            )
            # Log loss event
            event_service.log(
                EventType.MINESWEEPER,
                MinesweeperOutcome.LOST,
                user_id=request.user_id,
                chat_id=game.chat_id,
                card_id=game.bet_card_id,
                game_id=request.game_id,
                cells_revealed=len(revealed_cells),
                claim_points_earned=claim_points_earned,
            )
            # Loss: destroy the bet card
            asyncio.create_task(
                process_minesweeper_loss_background(
                    username=username,
                    chat_id=game.chat_id,
                    bet_card_id=game.bet_card_id,
                    card_title=card.title(include_rarity=True),
                )
            )

        return MinesweeperUpdateResponse(
            revealed_cells=revealed_cells,
            mine_positions=mine_positions,
            claim_point_positions=visible_claim_points,
            next_refresh_time=next_refresh_time,
            status=updated_game.status,
            bet_card_rarity=card.rarity,
            source_display_name=source_display_name,
            claim_point_awarded=claim_point_awarded,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error updating minesweeper game: %s", e)
        raise HTTPException(status_code=500, detail="Failed to update game")
