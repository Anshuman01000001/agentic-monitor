import logging
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker, declarative_base

logger = logging.getLogger(__name__)

Base = declarative_base()
_engine = None
_SessionLocal = None

from . import models  # noqa: F401


def _ensure_sqlite_columns(engine):
    if engine.url.get_backend_name() != "sqlite":
        return

    with engine.begin() as conn:
        inspector = inspect(conn)
        for table_name in Base.metadata.tables:
            if not inspector.has_table(table_name):
                continue

            existing_columns = {column["name"] for column in inspector.get_columns(table_name)}
            table = Base.metadata.tables[table_name]

            for column in table.columns:
                if column.name in existing_columns:
                    continue

                try:
                    column_type = column.type.compile(dialect=engine.dialect)
                    conn.execute(text(f"ALTER TABLE {table_name} ADD COLUMN {column.name} {column_type}"))
                    logger.info("Added missing column %s.%s", table_name, column.name)
                except Exception as exc:
                    logger.warning("Could not add column %s.%s: %s", table_name, column.name, exc)


def init_db(database_url: str = "sqlite:///./monitor.db"):
    global _engine, _SessionLocal

    if _engine is not None:
        _engine.dispose()

    _engine = create_engine(database_url, connect_args={"check_same_thread": False})
    _SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=_engine)
    Base.metadata.create_all(bind=_engine)
    _ensure_sqlite_columns(_engine)
    logger.info("Database initialized at %s", database_url)


def get_engine():
    return _engine


def get_session():
    return _SessionLocal()
