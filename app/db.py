"""SQLAlchemy engine, session, and database bootstrap."""

from __future__ import annotations

from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app import config
from app.logging_config import get_logger

logger = get_logger(__name__)

engine = create_engine(config.DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)


class Base(DeclarativeBase):
    pass


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    """Create tables, migrate, and seed branches / branch users."""
    # Import models so metadata is registered.
    from app import models  # noqa: F401
    from app.db_migrate import (
        migrate_application_form_fields,
        migrate_application_status,
        migrate_branch_entries,
        migrate_document_archives,
        migrate_signature_records,
        migrate_verifications,
    )
    from app.seed import seed_branches_and_users

    Base.metadata.create_all(bind=engine)
    try:
        migrate_application_status(engine)
        migrate_application_form_fields(engine)
        migrate_branch_entries(engine)
        migrate_document_archives(engine)
        migrate_signature_records(engine)
        migrate_verifications(engine)
    except Exception:
        logger.exception("Schema migration failed")
        raise

    db = SessionLocal()
    try:
        seed_branches_and_users(db)
        from app.models import BranchEntryDocument, DocumentArchive
        from app.services.document_archive import backfill_branch_documents

        if db.query(DocumentArchive).count() == 0:
            has_text = (
                db.query(BranchEntryDocument)
                .filter(BranchEntryDocument.extracted_text.isnot(None))
                .filter(BranchEntryDocument.extracted_text != "")
                .count()
            )
            if has_text:
                backfill_branch_documents(db)
        db.commit()
        logger.info("Database initialized and seeded")
    except Exception:
        db.rollback()
        logger.exception("Database seed failed")
        raise
    finally:
        db.close()
