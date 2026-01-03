"""Service layer for gacha bot business logic.

This module provides service classes that encapsulate business logic
for various domain entities. Services use SQLAlchemy ORM directly
and return Pydantic DTOs from utils.schemas.

Available services:
- card_service: Card management (add, get, update, delete cards)
- user_service: User management (upsert, get users, chat membership)
- spin_service: Spin management (get, consume, refresh spins)
- claim_service: Claim point management (get, increment, reduce)
- character_service: Character management (add, get, update characters)
- rolled_card_service: Rolled card tracking (create, update, expiry)
- thread_service: Thread ID management for chats
- set_service: Card set management
"""

from utils.services.card_service import (
    add_card,
    add_card_from_generated,
    delete_card,
    delete_cards,
    get_all_cards,
    get_all_users_with_cards,
    get_card,
    get_card_image,
    get_card_images_batch,
    get_modifier_counts_for_chat,
    get_total_cards_count,
    get_unique_modifiers,
    get_user_card_count,
    get_user_cards_by_rarity,
    get_user_collection,
    get_user_stats,
    nullify_card_owner,
    set_card_locked,
    set_card_owner,
    swap_card_owners,
    try_claim_card,
    update_card_file_id,
    update_card_image,
    clear_all_file_ids,
)

from utils.services.user_service import (
    add_user_to_chat,
    get_all_chat_users,
    get_all_chat_users_with_profile,
    get_chat_users_and_characters,
    get_most_frequent_chat_id_for_user,
    get_random_chat_user_with_profile,
    get_user,
    get_user_id_by_username,
    get_username_for_user_id,
    is_user_in_chat,
    remove_user_from_chat,
    update_user_profile,
    upsert_user,
    user_exists,
)

from utils.services.spin_service import (
    consume_user_spin,
    decrement_user_spins,
    get_next_spin_refresh,
    get_or_update_user_spins_with_daily_refresh,
    get_user_spins,
    increment_user_spins,
    update_user_spins,
)

from utils.services.claim_service import (
    get_claim_balance,
    increment_claim_balance,
    reduce_claim_points,
    set_all_claim_balances_to,
)

from utils.services.character_service import (
    add_character,
    delete_characters_by_name,
    get_character_by_id,
    get_character_by_name,
    get_characters_by_chat,
    update_character_image,
)

from utils.services.rolled_card_service import (
    create_rolled_card,
    delete_rolled_card,
    get_rolled_card,
    get_rolled_card_by_card_id,
    get_rolled_card_by_roll_id,
    is_rolled_card_reroll_expired,
    set_rolled_card_being_rerolled,
    set_rolled_card_locked,
    set_rolled_card_rerolled,
    update_rolled_card_attempted_by,
)

from utils.services.thread_service import (
    clear_thread_ids,
    get_thread_id,
    set_thread_id,
)

from utils.services.set_service import (
    get_set_id_by_name,
    upsert_set,
)

from utils.services.roll_service import (
    can_roll,
    get_last_roll_time,
    record_roll,
)

from utils.services.rtb_service import (
    create_game as rtb_create_game,
    cash_out as rtb_cash_out,
    check_availability as rtb_check_availability,
    get_active_game as rtb_get_active_game,
    get_existing_game as rtb_get_existing_game,
    get_game_by_id as rtb_get_game_by_id,
    get_cooldown_end_time as rtb_get_cooldown_end_time,
    process_guess as rtb_process_guess,
    set_debug_mode as rtb_set_debug_mode,
)

from utils.services import event_service

from utils.services.achievement_service import (
    get_achievement_by_name,
    get_achievement_by_id,
    get_all_achievements,
    register_achievement,
    sync_achievement,
    update_achievement_icon,
    has_achievement,
    grant_achievement,
    get_user_achievements,
    get_achievement_holders,
)

from settings.constants import (
    RTB_CARDS_PER_GAME,
    RTB_MIN_BET,
    RTB_MAX_BET,
    RTB_MULTIPLIER_PROGRESSION,
    RARITY_ORDER,
)

__all__ = [
    # Card service
    "add_card",
    "add_card_from_generated",
    "delete_card",
    "delete_cards",
    "get_all_cards",
    "get_all_users_with_cards",
    "get_card",
    "get_card_image",
    "get_card_images_batch",
    "get_modifier_counts_for_chat",
    "get_total_cards_count",
    "get_unique_modifiers",
    "get_user_card_count",
    "get_user_cards_by_rarity",
    "get_user_collection",
    "get_user_stats",
    "nullify_card_owner",
    "set_card_locked",
    "set_card_owner",
    "swap_card_owners",
    "try_claim_card",
    "update_card_file_id",
    "update_card_image",
    "clear_all_file_ids",
    # User service
    "add_user_to_chat",
    "get_all_chat_users",
    "get_all_chat_users_with_profile",
    "get_chat_users_and_characters",
    "get_most_frequent_chat_id_for_user",
    "get_random_chat_user_with_profile",
    "get_user",
    "get_user_id_by_username",
    "get_username_for_user_id",
    "is_user_in_chat",
    "remove_user_from_chat",
    "update_user_profile",
    "upsert_user",
    "user_exists",
    # Spin service
    "consume_user_spin",
    "decrement_user_spins",
    "get_next_spin_refresh",
    "get_or_update_user_spins_with_daily_refresh",
    "get_user_spins",
    "increment_user_spins",
    "update_user_spins",
    # Claim service
    "get_claim_balance",
    "increment_claim_balance",
    "reduce_claim_points",
    "set_all_claim_balances_to",
    # Character service
    "add_character",
    "delete_characters_by_name",
    "get_character_by_id",
    "get_character_by_name",
    "get_characters_by_chat",
    "update_character_image",
    # Rolled card service
    "create_rolled_card",
    "delete_rolled_card",
    "get_rolled_card",
    "get_rolled_card_by_card_id",
    "get_rolled_card_by_roll_id",
    "is_rolled_card_reroll_expired",
    "set_rolled_card_being_rerolled",
    "set_rolled_card_locked",
    "set_rolled_card_rerolled",
    "update_rolled_card_attempted_by",
    # Thread service
    "clear_thread_ids",
    "get_thread_id",
    "set_thread_id",
    # Set service
    "get_set_id_by_name",
    "upsert_set",
    # Roll service
    "can_roll",
    "get_last_roll_time",
    "record_roll",
    # RTB (Ride the Bus) service
    "rtb_check_availability",
    "rtb_create_game",
    "rtb_cash_out",
    "rtb_get_active_game",
    "rtb_get_existing_game",
    "rtb_get_game_by_id",
    "rtb_get_cooldown_end_time",
    "rtb_process_guess",
    "rtb_set_debug_mode",
    "RTB_CARDS_PER_GAME",
    "RTB_MIN_BET",
    "RTB_MAX_BET",
    "RTB_MULTIPLIER_PROGRESSION",
    "RARITY_ORDER",
    # Event service
    "event_service",
    # Achievement service
    "get_achievement_by_name",
    "get_achievement_by_id",
    "get_all_achievements",
    "register_achievement",
    "sync_achievement",
    "update_achievement_icon",
    "has_achievement",
    "grant_achievement",
    "get_user_achievements",
    "get_achievement_holders",
]
