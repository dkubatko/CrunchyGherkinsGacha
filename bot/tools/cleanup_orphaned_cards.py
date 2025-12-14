#!/usr/bin/env python3
"""Cleanup script to delete orphaned cards (cards without an owner).

This script deletes all cards that have no owner (owner IS NULL) along with
their associated entries in related tables (rolled_cards, minesweeper_games).

Usage:
    python -m tools.cleanup_orphaned_cards [--dry-run] [--verbose]

Options:
    --dry-run   Show what would be deleted without actually deleting
    --verbose   Show detailed information about each card being deleted
"""

import argparse
import logging
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from utils.session import get_session
from utils.models import CardModel, RolledCardModel, MinesweeperGameModel

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)
logger = logging.getLogger(__name__)


def get_orphaned_cards(session, verbose: bool = False) -> list:
    """Get all cards without an owner."""
    orphaned = session.query(CardModel).filter(CardModel.owner.is_(None)).all()

    if verbose:
        for card in orphaned:
            logger.info(
                f"  Card {card.id}: {card.modifier or ''} {card.base_name} ({card.rarity}) "
                f"- chat_id={card.chat_id}"
            )

    return orphaned


def get_related_rolled_cards(session, card_ids: list) -> list:
    """Get rolled_cards entries that reference any of the given card IDs."""
    if not card_ids:
        return []

    return (
        session.query(RolledCardModel)
        .filter(
            (RolledCardModel.original_card_id.in_(card_ids))
            | (RolledCardModel.rerolled_card_id.in_(card_ids))
        )
        .all()
    )


def get_related_minesweeper_games(session, card_ids: list) -> list:
    """Get minesweeper_games entries that reference any of the given card IDs."""
    if not card_ids:
        return []

    return (
        session.query(MinesweeperGameModel)
        .filter(
            (MinesweeperGameModel.bet_card_id.in_(card_ids))
            | (MinesweeperGameModel.reward_card_id.in_(card_ids))
        )
        .all()
    )


def cleanup_orphaned_cards(dry_run: bool = False, verbose: bool = False) -> dict:
    """
    Delete all orphaned cards and their related entries.

    Args:
        dry_run: If True, only report what would be deleted without actually deleting
        verbose: If True, show detailed information about each item

    Returns:
        Dictionary with counts of deleted items
    """
    with get_session(commit=not dry_run) as session:
        # Get orphaned cards
        orphaned_cards = get_orphaned_cards(session, verbose)
        card_ids = [card.id for card in orphaned_cards]

        if not card_ids:
            logger.info("No orphaned cards found.")
            return {"cards": 0, "rolled_cards": 0, "minesweeper_games": 0}

        logger.info(f"Found {len(card_ids)} orphaned cards")

        # Get related entries
        related_rolled = get_related_rolled_cards(session, card_ids)
        related_minesweeper = get_related_minesweeper_games(session, card_ids)

        if verbose:
            if related_rolled:
                logger.info(f"Related rolled_cards entries:")
                for rc in related_rolled:
                    logger.info(
                        f"  roll_id={rc.roll_id}, original_card_id={rc.original_card_id}, "
                        f"rerolled_card_id={rc.rerolled_card_id}"
                    )

            if related_minesweeper:
                logger.info(f"Related minesweeper_games entries:")
                for mg in related_minesweeper:
                    logger.info(
                        f"  game_id={mg.id}, bet_card_id={mg.bet_card_id}, "
                        f"reward_card_id={mg.reward_card_id}, status={mg.status}"
                    )

        counts = {
            "cards": len(card_ids),
            "rolled_cards": len(related_rolled),
            "minesweeper_games": len(related_minesweeper),
        }

        if dry_run:
            logger.info(f"[DRY RUN] Would delete:")
            logger.info(f"  - {counts['rolled_cards']} rolled_cards entries")
            logger.info(f"  - {counts['minesweeper_games']} minesweeper_games entries")
            logger.info(f"  - {counts['cards']} cards")
            return counts

        # Delete in order: related tables first, then cards
        # Delete rolled_cards
        if card_ids:
            deleted_rolled = (
                session.query(RolledCardModel)
                .filter(
                    (RolledCardModel.original_card_id.in_(card_ids))
                    | (RolledCardModel.rerolled_card_id.in_(card_ids))
                )
                .delete(synchronize_session=False)
            )
            logger.info(f"Deleted {deleted_rolled} rolled_cards entries")

        # Delete minesweeper_games
        if card_ids:
            deleted_minesweeper = (
                session.query(MinesweeperGameModel)
                .filter(
                    (MinesweeperGameModel.bet_card_id.in_(card_ids))
                    | (MinesweeperGameModel.reward_card_id.in_(card_ids))
                )
                .delete(synchronize_session=False)
            )
            logger.info(f"Deleted {deleted_minesweeper} minesweeper_games entries")

        # Delete cards
        deleted_cards = (
            session.query(CardModel)
            .filter(CardModel.id.in_(card_ids))
            .delete(synchronize_session=False)
        )
        logger.info(f"Deleted {deleted_cards} orphaned cards")

        return counts


def main():
    parser = argparse.ArgumentParser(
        description="Delete orphaned cards (cards without an owner) and related entries."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be deleted without actually deleting",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Show detailed information about each item being deleted",
    )

    args = parser.parse_args()

    if args.dry_run:
        logger.info("Running in DRY RUN mode - no changes will be made")

    try:
        counts = cleanup_orphaned_cards(dry_run=args.dry_run, verbose=args.verbose)

        total = sum(counts.values())
        if total > 0:
            action = "Would delete" if args.dry_run else "Deleted"
            logger.info(f"\n{action} {total} total entries:")
            for table, count in counts.items():
                if count > 0:
                    logger.info(f"  - {table}: {count}")

        return 0
    except Exception as e:
        logger.error(f"Error during cleanup: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
