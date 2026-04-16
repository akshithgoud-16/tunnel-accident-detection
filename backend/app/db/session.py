from collections.abc import Generator
import logging

from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings

settings = get_settings()

logger = logging.getLogger(__name__)


def _create_engine_with_fallback():
    primary_url = settings.database_url
    primary_engine = create_engine(primary_url, pool_pre_ping=True)

    try:
        with primary_engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        logger.info("Connected to primary database: %s", primary_url)
        return primary_engine
    except SQLAlchemyError as exc:
        fallback_url = "sqlite:///./backend/app/dev.db"
        logger.warning(
            "Primary database connection failed (%s). Falling back to SQLite at %s",
            exc,
            fallback_url,
        )
        return create_engine(
            fallback_url,
            connect_args={"check_same_thread": False},
            pool_pre_ping=True,
        )

engine = _create_engine_with_fallback()
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
