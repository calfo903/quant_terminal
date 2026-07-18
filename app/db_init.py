"""Bootstrap the relational schema (idempotent).



Creates the tables (via SQLAlchemy metadata) and converts the time-series

tables into TimescaleDB hypertables. Run once (or in CI) with:



    python -m app.db_init



Requires TIMESCALEDB_URL to point at a Postgres instance with the

timescaledb extension available.

"""

import asyncio

import logging



from sqlalchemy import text



from app.core.database import Base, timescale_engine

from app.core import models  # noqa: F401  (registers models on Base.metadata)



logging.basicConfig(level=logging.INFO)

logger = logging.getLogger("db_init")





async def create_schema() -> None:

    # TimescaleDB extension (no-op if already present).

    async with timescale_engine.begin() as conn:

        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS timescaledb;"))



    # Create all tables.

    async with timescale_engine.begin() as conn:

        await conn.run_sync(Base.metadata.create_all)



    # Convert time-series tables into hypertables.

    async with timescale_engine.begin() as conn:

        for table in ("candles", "ticks"):

            await conn.execute(

                text(

                    f"SELECT create_hypertable('{table}', 'time', "

                    f"if_not_exists => TRUE);"

                )

            )



    logger.info("Schema initialized (candles, ticks, image_analyses, predictions, trades)")





if __name__ == "__main__":

    asyncio.run(create_schema())
