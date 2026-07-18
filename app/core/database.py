from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker

from sqlalchemy.pool import QueuePool

from sqlalchemy.orm import declarative_base

from redis.asyncio import Redis

from app.core.config import settings

import logging



logger = logging.getLogger(__name__)



Base = declarative_base()



timescale_engine = create_async_engine(

    settings.TIMESCALEDB_URL,

    poolclass=QueuePool,

    pool_size=20,

    max_overflow=10,

    pool_pre_ping=True,

    pool_recycle=3600,

    echo=settings.DEBUG,

)



TimescaleSession = async_sessionmaker(

    timescale_engine,

    class_=AsyncSession,

    expire_on_commit=False,

)



# Module-level singleton. `init_redis()` reassigns this name inside THIS module,

# so callers must always access it through `get_redis()` (never bind the value

# at import time, or they will keep seeing `None`).

redis_client: Redis = None





async def init_redis() -> Redis:

    global redis_client

    redis_client = Redis.from_url(

        settings.REDIS_URL,

        encoding="utf-8",

        decode_responses=True,

        max_connections=20,

    )

    await redis_client.ping()

    logger.info("Redis connection established")

    return redis_client





def get_redis() -> Redis:

    """Return the live Redis client (or None before init). Always use this

    accessor instead of importing `redis_client` directly."""

    return redis_client





async def get_db() -> AsyncSession:

    async with TimescaleSession() as session:

        try:

            yield session

            await session.commit()

        except Exception:

            await session.rollback()

            raise

        finally:

            await session.close()





async def close_connections():

    global redis_client

    await timescale_engine.dispose()

    if redis_client:

        await redis_client.close()

    logger.info("Database connections closed")
