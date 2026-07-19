import logging
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

logger = logging.getLogger(__name__)

Base = declarative_base()
_engine = None
_SessionLocal = None


def init_db(database_url: str = "sqlite:///./monitor.db"):
    global _engine, _SessionLocal
    if _engine is None:
        _engine = create_engine(database_url, connect_args={"check_same_thread": False})
        _SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=_engine)
        Base.metadata.create_all(bind=_engine)
        logger.info("Database initialized at %s", database_url)


def get_engine():
    return _engine


def get_session():
    return _SessionLocal()
