import asyncio

import os

import sys

from logging.config import fileConfig



from alembic import context

from sqlalchemy import pool

from sqlalchemy.ext.asyncio import create_async_engine



# Make the project importable when `alembic` is run from the repo root.

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))



from app.core.config import settings  # noqa: E402

from app.core.database import Base  # noqa: E402

from app.core import models  # noqa: F401  (register ORM models on Base.metadata)  # noqa: E402



config = context.config



if config.config_file_name is not None:

    fileConfig(config.config_file_name)



# Never hardcode the URL. Pull it from app settings so it matches the

# TIMESCALEDB_URL supplied via environment / .env in every environment.

config.set_main_option("sqlalchemy.url", settings.TIMESCALEDB_URL)



target_metadata = Base.metadata





def run_migrations_offline() -> None:

    context.configure(

        url=settings.TIMESCALEDB_URL,

        target_metadata=target_metadata,

        literal_binds=True,

        dialect_opts={"paramstyle": "named"},

        compare_type=True,

    )

    with context.begin_transaction():

        context.run_migrations()





def do_run_migrations(connection) -> None:

    context.configure(

        connection=connection,

        target_metadata=target_metadata,

        compare_type=True,

        compare_server_default=True,

    )

    with context.begin_transaction():

        context.run_migrations()





async def run_migrations_online() -> None:

    connectable = create_async_engine(settings.TIMESCALEDB_URL, poolclass=pool.NullPool)

    async with connectable.connect() as connection:

        await connection.run_sync(do_run_migrations)

    await connectable.dispose()





if context.is_offline_mode():

    run_migrations_offline()

else:

    asyncio.run(run_migrations_online())
