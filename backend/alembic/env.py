
import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, event, pool

from app.database import Base, DATABASE_URL
from app import models  # Registra todos los modelos


config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)


database_url = os.getenv("AGROSCAN_DATABASE_URL", DATABASE_URL)

config.set_main_option(
    "sqlalchemy.url",
    database_url.replace("%", "%%"),
)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")

    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    # Desactivar claves foraneas directamente en DBAPI,
    # antes de que SQLAlchemy inicie una transaccion.
    if connectable.dialect.name == "sqlite":

        @event.listens_for(connectable, "connect")
        def disable_foreign_keys(dbapi_connection, connection_record):
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=OFF")
            cursor.close()

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            render_as_batch=True,
        )

        # Alembic administra la transaccion de la migracion.
        with context.begin_transaction():
            context.run_migrations()

        if connection.dialect.name == "sqlite":

            # Verificar integridad despues de ejecutar la migracion.
            violations = connection.exec_driver_sql(
                "PRAGMA foreign_key_check"
            ).fetchall()

            if violations:
                raise RuntimeError(
                    f"Errores de integridad referencial: {violations}"
                )

            # Finalizar la transaccion de comprobacion.
            connection.commit()

            # Reactivar las claves foraneas fuera de una transaccion.
            connection.exec_driver_sql("PRAGMA foreign_keys=ON")
            connection.commit()

    connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
