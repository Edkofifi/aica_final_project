"""
Provides a single SQLAlchemy engine and a context-manager helper for
database connections.  All pipeline modules obtain their connection here.
"""

from contextlib import contextmanager
from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError
from utils.config import DB_URL
from utils.logger import get_logger

logger = get_logger(__name__)

_engine = None


def get_engine():
    """Return (and lazily create) the shared SQLAlchemy engine."""
    global _engine
    if _engine is None:
        _engine = create_engine(
            DB_URL,
            pool_size=5,          # keep 5 connections warm in the pool
            max_overflow=10,      # allow up to 10 extra under load
            pool_pre_ping=True,   # test connection health before checkout
            echo=False,
        )
        logger.info(f"Database engine created: {DB_URL.split('@')[-1]}")  # hide credentials in log
    return _engine


@contextmanager
def get_connection():
    """
    Context manager yielding a raw psycopg2 connection.
    Commits on success, rolls back on any exception.

    Usage:
        with get_connection() as conn:
            cur = conn.cursor()
            cur.execute("INSERT INTO ...")
    """
    engine = get_engine()
    conn = engine.raw_connection()
    try:
        yield conn
        conn.commit()
    except Exception as exc:
        conn.rollback()
        logger.error(f"Database error — rolling back: {exc}")
        raise
    finally:
        conn.close()


def test_connection() -> bool:
    """Return True if the database is reachable, False otherwise."""
    try:
        with get_engine().connect() as conn:
            conn.execute(text("SELECT 1"))
        logger.info("Database connection test passed.")
        return True
    except Exception as exc:
        logger.error(f"Database connection test failed: {exc}")
        return False
