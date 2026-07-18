"""initial schema: candles, ticks, image_analyses, predictions, trades

Revision ID: 1a2b3c4d5e6f
Revises:
Create Date: 2024-01-01 00:00:00
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "1a2b3c4d5e6f"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS timescaledb")

    op.create_table(
        "candles",
        sa.Column("instrument", sa.String(), nullable=False),
        sa.Column("timeframe", sa.String(), nullable=False),
        sa.Column("time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("open", sa.Float(), nullable=True),
        sa.Column("high", sa.Float(), nullable=True),
        sa.Column("low", sa.Float(), nullable=True),
        sa.Column("close", sa.Float(), nullable=True),
        sa.Column("volume", sa.Float(), nullable=True),
        sa.PrimaryKeyConstraint("instrument", "timeframe", "time"),
    )

    op.create_table(
        "ticks",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("instrument", sa.String(), nullable=True),
        sa.Column("time", sa.DateTime(timezone=True), nullable=True),
        sa.Column("price", sa.Float(), nullable=True),
        sa.Column("quantity", sa.Float(), nullable=True),
        sa.Column("is_buy", sa.Boolean(), nullable=True),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_ticks_instrument", "ticks", ["instrument"])
    op.create_index("ix_ticks_time", "ticks", ["time"])
    op.create_index("ix_ticks_received_at", "ticks", ["received_at"])

    op.create_table(
        "image_analyses",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("model_version", sa.String(), nullable=True),
        sa.Column("image_size", sa.Integer(), nullable=True),
        sa.Column("analysis_result", postgresql.JSONB(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "predictions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("instrument", sa.String(), nullable=True),
        sa.Column("signal", sa.String(), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("model_version", sa.String(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_predictions_instrument", "predictions", ["instrument"])
    op.create_index("ix_predictions_created_at", "predictions", ["created_at"])

    op.create_table(
        "trades",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("instrument", sa.String(), nullable=True),
        sa.Column("side", sa.String(), nullable=True),
        sa.Column("size", sa.Float(), nullable=True),
        sa.Column("price", sa.Float(), nullable=True),
        sa.Column("pnl", sa.Float(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_trades_instrument", "trades", ["instrument"])
    op.create_index("ix_trades_created_at", "trades", ["created_at"])

    # Convert the time-series tables into TimescaleDB hypertables.
    op.execute("SELECT create_hypertable('candles', 'time', if_not_exists => TRUE)")
    op.execute("SELECT create_hypertable('ticks', 'time', if_not_exists => TRUE)")


def downgrade() -> None:
    op.drop_table("trades")
    op.drop_table("predictions")
    op.drop_table("image_analyses")
    op.drop_table("ticks")
    op.drop_table("candles")
