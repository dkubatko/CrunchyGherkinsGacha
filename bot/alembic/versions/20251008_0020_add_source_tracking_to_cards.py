"""Add source_type and source_id to cards table for tracking card generation source

Revision ID: 20251008_0020
Revises: 20251006_0019
Create Date: 2025-10-08 00:00:00.000000

"""

from __future__ import annotations

from difflib import SequenceMatcher
from alembic import op
import sqlalchemy as sa
from sqlalchemy import text

# revision identifiers, used by Alembic.
revision = "20251008_0020"
down_revision = "20251006_0019"
branch_labels = None
depends_on = None


def find_best_matching_source_id(
    target_name: str,
    user_sources: list[tuple[int, str]],
    character_sources: list[tuple[int, str]],
    min_similarity: float = 0.6,
) -> tuple[str | None, int | None]:
    """
    Find the best matching source by name using fuzzy matching.

    Args:
        target_name: The name to match against
        user_sources: List of (user_id, display_name) tuples
        character_sources: List of (character_id, name) tuples
        min_similarity: Minimum similarity threshold (0.0 to 1.0)

    Returns:
        Tuple of (source_type, source_id) or (None, None) if no match found
    """
    target_name_lower = target_name.strip().lower()
    best_source_type = None
    best_source_id = None
    best_similarity = 0.0

    # Check user sources first
    for user_id, display_name in user_sources:
        if not display_name:
            continue
        src_name_lower = display_name.strip().lower()

        # Exact match (case-insensitive) gets priority
        if src_name_lower == target_name_lower:
            return ("user", user_id)

        # Calculate similarity ratio
        similarity = SequenceMatcher(None, target_name_lower, src_name_lower).ratio()
        if similarity > best_similarity:
            best_similarity = similarity
            best_source_type = "user"
            best_source_id = user_id

    # Check character sources
    for character_id, name in character_sources:
        if not name:
            continue
        src_name_lower = name.strip().lower()

        # Exact match (case-insensitive) gets priority
        if src_name_lower == target_name_lower:
            return ("character", character_id)

        # Calculate similarity ratio
        similarity = SequenceMatcher(None, target_name_lower, src_name_lower).ratio()
        if similarity > best_similarity:
            best_similarity = similarity
            best_source_type = "character"
            best_source_id = character_id

    # Return best match only if it meets the minimum similarity threshold
    if best_similarity >= min_similarity:
        return (best_source_type, best_source_id)

    return (None, None)


def upgrade() -> None:
    # Add source_type and source_id columns to cards table
    with op.batch_alter_table("cards", schema=None) as batch_op:
        batch_op.add_column(sa.Column("source_type", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("source_id", sa.Integer(), nullable=True))

    # Backfill source information for existing cards
    connection = op.get_bind()

    # Get all cards
    cards_result = connection.execute(text("SELECT id, base_name, chat_id FROM cards"))
    cards = cards_result.fetchall()

    print(f"Backfilling source information for {len(cards)} cards...")

    matched_count = 0
    unmatched_count = 0

    for card in cards:
        card_id, base_name, chat_id = card

        if not chat_id:
            unmatched_count += 1
            continue

        # Get all users from this chat with profiles
        users_result = connection.execute(
            text(
                """
                SELECT u.user_id, u.display_name 
                FROM users u
                INNER JOIN chats c ON c.user_id = u.user_id
                WHERE c.chat_id = :chat_id 
                AND u.display_name IS NOT NULL 
                AND u.profile_imageb64 IS NOT NULL
            """
            ),
            {"chat_id": chat_id},
        )
        user_sources = [(row[0], row[1]) for row in users_result.fetchall()]

        # Get all characters from this chat
        characters_result = connection.execute(
            text(
                """
                SELECT id, name 
                FROM characters 
                WHERE chat_id = :chat_id
                AND name IS NOT NULL
                AND imageb64 IS NOT NULL
            """
            ),
            {"chat_id": chat_id},
        )
        character_sources = [(row[0], row[1]) for row in characters_result.fetchall()]

        # Find best matching source
        source_type, source_id = find_best_matching_source_id(
            base_name, user_sources, character_sources, min_similarity=0.2
        )

        if source_type and source_id:
            connection.execute(
                text(
                    """
                    UPDATE cards 
                    SET source_type = :source_type, source_id = :source_id 
                    WHERE id = :card_id
                """
                ),
                {"source_type": source_type, "source_id": source_id, "card_id": card_id},
            )
            matched_count += 1
        else:
            unmatched_count += 1

    print(f"Backfill complete: {matched_count} matched, {unmatched_count} unmatched")


def downgrade() -> None:
    with op.batch_alter_table("cards", schema=None) as batch_op:
        batch_op.drop_column("source_id")
        batch_op.drop_column("source_type")
