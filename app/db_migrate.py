"""Lightweight schema/data migrations run on startup."""

from __future__ import annotations

from sqlalchemy import text

from app.logging_config import get_logger

logger = get_logger(__name__)

STATUS_RENAMES = {
    "submitted": "pending",
    "analyzed": "completed",
    "approved": "accepted",
}

# New / renamed application columns (idempotent ADD / RENAME).
APPLICATION_COLUMNS = {
    "age": "VARCHAR(16) NOT NULL DEFAULT ''",
    "cnic_full_name": "VARCHAR(255) NOT NULL DEFAULT ''",
    "cnic_issue_date": "VARCHAR(64) NOT NULL DEFAULT ''",
    "cnic_expiry_date": "VARCHAR(64) NOT NULL DEFAULT ''",
    "country_to_stay": "VARCHAR(128) NOT NULL DEFAULT ''",
    "gender": "VARCHAR(32) NOT NULL DEFAULT ''",
    "designation": "VARCHAR(128) NOT NULL DEFAULT ''",
}


def _column_exists(conn, table: str, column: str) -> bool:
    row = conn.execute(
        text(
            """
            SELECT 1
            FROM information_schema.columns
            WHERE table_name = :table AND column_name = :column
            """
        ),
        {"table": table, "column": column},
    ).first()
    return row is not None


def migrate_application_status(engine) -> None:
    """Normalize application status to pending/analyzing/completed/accepted/rejected."""
    with engine.begin() as conn:
        # Convert enum column to varchar if needed (Postgres).
        col = conn.execute(
            text(
                """
                SELECT data_type, udt_name
                FROM information_schema.columns
                WHERE table_name = 'applications' AND column_name = 'status'
                """
            )
        ).first()
        if not col:
            return

        data_type, udt_name = col
        if data_type == "USER-DEFINED" or udt_name == "application_status":
            conn.execute(
                text(
                    "ALTER TABLE applications "
                    "ALTER COLUMN status TYPE VARCHAR(32) USING status::text"
                )
            )
            logger.info("Migrated applications.status to VARCHAR")

        for old, new in STATUS_RENAMES.items():
            result = conn.execute(
                text("UPDATE applications SET status = :new WHERE status = :old"),
                {"old": old, "new": new},
            )
            if result.rowcount:
                logger.info("Renamed status %s -> %s (%s rows)", old, new, result.rowcount)

        # Drop old enum type if unused.
        try:
            conn.execute(text("DROP TYPE IF EXISTS application_status"))
        except Exception:
            pass


def migrate_application_form_fields(engine) -> None:
    """Add multi-phase form columns and backfill from legacy fields."""
    with engine.begin() as conn:
        if not _column_exists(conn, "applications", "id"):
            return

        for name, ddl in APPLICATION_COLUMNS.items():
            if name == "designation":
                continue  # handled below with occupation rename
            if _column_exists(conn, "applications", name):
                continue
            conn.execute(text(f"ALTER TABLE applications ADD COLUMN {name} {ddl}"))
            logger.info("Added applications.%s", name)

        # occupation → designation (prefer rename; drop leftover occupation)
        has_occupation = _column_exists(conn, "applications", "occupation")
        has_designation = _column_exists(conn, "applications", "designation")
        if has_occupation and not has_designation:
            conn.execute(
                text("ALTER TABLE applications RENAME COLUMN occupation TO designation")
            )
            logger.info("Renamed applications.occupation -> designation")
        elif not has_designation:
            conn.execute(
                text(
                    "ALTER TABLE applications ADD COLUMN designation "
                    "VARCHAR(128) NOT NULL DEFAULT ''"
                )
            )
            logger.info("Added applications.designation")
        elif has_occupation:
            conn.execute(
                text(
                    "UPDATE applications SET designation = occupation "
                    "WHERE (designation IS NULL OR designation = '') "
                    "AND occupation IS NOT NULL AND occupation <> ''"
                )
            )
            conn.execute(text("ALTER TABLE applications DROP COLUMN occupation"))
            logger.info("Dropped legacy applications.occupation after backfill")

        # Backfill CNIC full name from personal full name for older rows
        if _column_exists(conn, "applications", "cnic_full_name"):
            conn.execute(
                text(
                    "UPDATE applications SET cnic_full_name = full_name "
                    "WHERE cnic_full_name IS NULL OR cnic_full_name = ''"
                )
            )

        # Make legacy address optional if still present
        if _column_exists(conn, "applications", "address"):
            try:
                conn.execute(
                    text("ALTER TABLE applications ALTER COLUMN address DROP NOT NULL")
                )
            except Exception:
                pass


def migrate_branch_entries(engine) -> None:
    """Ensure branch_entries tables exist (create_all covers new installs)."""
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS branch_entries (
                    id UUID PRIMARY KEY,
                    branch_id INTEGER NOT NULL REFERENCES branches(id),
                    created_by INTEGER REFERENCES users(id),
                    customer_name VARCHAR(255) NOT NULL,
                    created_at TIMESTAMP NOT NULL DEFAULT NOW()
                )
                """
            )
        )
        conn.execute(
            text(
                """
                CREATE INDEX IF NOT EXISTS ix_branch_entries_branch_id
                ON branch_entries (branch_id)
                """
            )
        )
        conn.execute(
            text(
                """
                CREATE INDEX IF NOT EXISTS ix_branch_entries_created_at
                ON branch_entries (created_at)
                """
            )
        )
        conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS branch_entry_documents (
                    id UUID PRIMARY KEY,
                    branch_entry_id UUID NOT NULL REFERENCES branch_entries(id),
                    document_type VARCHAR(64) NOT NULL,
                    original_filename VARCHAR(255) NOT NULL DEFAULT '',
                    file_path VARCHAR(512) NOT NULL,
                    extracted_text TEXT,
                    fields_json JSONB,
                    checkboxes_json JSONB,
                    summary_json JSONB,
                    created_at TIMESTAMP NOT NULL DEFAULT NOW()
                )
                """
            )
        )
        conn.execute(
            text(
                """
                CREATE INDEX IF NOT EXISTS ix_branch_entry_documents_entry_id
                ON branch_entry_documents (branch_entry_id)
                """
            )
        )
        logger.info("Ensured branch_entries schema")


def migrate_signature_records(engine) -> None:
    """Ensure signature_records table exists for Signature Scan."""
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS signature_records (
                    id UUID PRIMARY KEY,
                    account_number VARCHAR(64) NOT NULL,
                    customer_name VARCHAR(255),
                    original_filename VARCHAR(255) NOT NULL DEFAULT '',
                    file_path VARCHAR(512) NOT NULL,
                    branch_id INTEGER NOT NULL REFERENCES branches(id),
                    created_by INTEGER REFERENCES users(id),
                    updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
                    created_at TIMESTAMP NOT NULL DEFAULT NOW()
                )
                """
            )
        )
        conn.execute(
            text(
                """
                CREATE UNIQUE INDEX IF NOT EXISTS uq_signature_account_number
                ON signature_records (account_number)
                """
            )
        )
        conn.execute(
            text(
                """
                CREATE INDEX IF NOT EXISTS ix_signature_records_account_number
                ON signature_records (account_number)
                """
            )
        )
        conn.execute(
            text(
                """
                CREATE INDEX IF NOT EXISTS ix_signature_records_branch_id
                ON signature_records (branch_id)
                """
            )
        )
        conn.execute(
            text(
                """
                CREATE INDEX IF NOT EXISTS ix_signature_records_created_at
                ON signature_records (created_at)
                """
            )
        )
        logger.info("Ensured signature_records schema")
