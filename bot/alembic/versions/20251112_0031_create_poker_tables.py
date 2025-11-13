"""Create poker_games and poker_players tables

Revision ID: 20251112_0031
Revises: 20251026_0030
Create Date: 2025-11-12

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "20251112_0031"
down_revision: Union[str, None] = "20251026_0030"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create poker_games and poker_players tables."""

    # Create poker_games table
    op.create_table(
        "poker_games",
        sa.Column("id", sa.Integer(), nullable=False, primary_key=True, autoincrement=True),
        sa.Column("chat_id", sa.String(), nullable=False),
        sa.Column(
            "status",
            sa.String(),
            nullable=False,
            server_default="waiting",
            comment="Game state: waiting, countdown, pre_flop, flop, turn, river, showdown, completed",
        ),
        sa.Column(
            "pot", sa.Integer(), nullable=False, server_default="0", comment="Total pot in spins"
        ),
        sa.Column(
            "current_bet",
            sa.Integer(),
            nullable=False,
            server_default="0",
            comment="Current bet to match",
        ),
        sa.Column(
            "min_betting_balance",
            sa.Integer(),
            nullable=True,
            comment="Equalized betting balance (min of all players' balances)",
        ),
        sa.Column(
            "community_cards",
            sa.String(),
            nullable=False,
            server_default="[]",
            comment="JSON array of community cards: [{source_id, source_type, rarity}, ...]",
        ),
        sa.Column(
            "countdown_start_time",
            sa.DateTime(),
            nullable=True,
            comment="When 60s countdown started (for countdown status)",
        ),
        sa.Column(
            "current_player_turn",
            sa.Integer(),
            nullable=True,
            comment="User ID of player whose turn it is",
        ),
        sa.Column(
            "dealer_position",
            sa.Integer(),
            nullable=True,
            comment="Seat index of dealer (for turn order)",
        ),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
    )

    # Create poker_players table (many players per game)
    op.create_table(
        "poker_players",
        sa.Column("id", sa.Integer(), nullable=False, primary_key=True, autoincrement=True),
        sa.Column("game_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("chat_id", sa.String(), nullable=False),
        sa.Column(
            "seat_position",
            sa.Integer(),
            nullable=False,
            comment="Position around table (0-based index)",
        ),
        sa.Column(
            "spin_balance",
            sa.Integer(),
            nullable=False,
            comment="Player's total spin balance when joined",
        ),
        sa.Column(
            "betting_balance",
            sa.Integer(),
            nullable=False,
            comment="Available balance for this game (equalized)",
        ),
        sa.Column(
            "current_bet",
            sa.Integer(),
            nullable=False,
            server_default="0",
            comment="Amount player has bet in current round",
        ),
        sa.Column(
            "total_bet",
            sa.Integer(),
            nullable=False,
            server_default="0",
            comment="Total amount bet across all rounds",
        ),
        sa.Column(
            "hole_cards",
            sa.String(),
            nullable=False,
            server_default="[]",
            comment="JSON array: [{source_id, source_type, rarity}, {source_id, source_type, rarity}]",
        ),
        sa.Column(
            "status",
            sa.String(),
            nullable=False,
            server_default="active",
            comment="Player state: active, folded, all_in, out",
        ),
        sa.Column(
            "last_action",
            sa.String(),
            nullable=True,
            comment="Last action taken: check, raise, fold, all_in",
        ),
        sa.Column("joined_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )

    # Indexes for poker_games
    op.create_index("idx_poker_games_chat_status", "poker_games", ["chat_id", "status"])
    op.create_index("idx_poker_games_status", "poker_games", ["status"])
    op.create_index("idx_poker_games_created", "poker_games", ["created_at"])

    # Indexes for poker_players
    op.create_index("idx_poker_players_game", "poker_players", ["game_id"])
    op.create_index("idx_poker_players_user", "poker_players", ["user_id"])
    op.create_index("idx_poker_players_game_user", "poker_players", ["game_id", "user_id"])
    op.create_index("idx_poker_players_user_chat", "poker_players", ["user_id", "chat_id"])


def downgrade() -> None:
    """Drop poker tables."""
    # Drop indexes first
    op.drop_index("idx_poker_players_user_chat", table_name="poker_players")
    op.drop_index("idx_poker_players_game_user", table_name="poker_players")
    op.drop_index("idx_poker_players_user", table_name="poker_players")
    op.drop_index("idx_poker_players_game", table_name="poker_players")

    op.drop_index("idx_poker_games_created", table_name="poker_games")
    op.drop_index("idx_poker_games_status", table_name="poker_games")
    op.drop_index("idx_poker_games_chat_status", table_name="poker_games")

    # Drop tables
    op.drop_table("poker_players")
    op.drop_table("poker_games")
