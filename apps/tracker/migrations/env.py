from alembic import context
from sqlalchemy import create_engine
from sqlalchemy.pool import NullPool

from apps.tracker.src.tracker.db import database_url


def run_migrations_offline() -> None:
    context.configure(dialect_name="postgresql", literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    engine = create_engine(database_url(), poolclass=NullPool, hide_parameters=True)
    try:
        with engine.connect() as connection:
            context.configure(connection=connection)
            with context.begin_transaction():
                context.run_migrations()
    finally:
        engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
