"""Small local migrations for SQLite installs.

The project intentionally avoids a full migration framework for the local-first
desktop workflow, but existing SQLite databases still need additive schema
changes when the ORM grows. These migrations only add columns and leave user
data untouched.
"""

from __future__ import annotations

from sqlalchemy.engine import Connection


SQLITE_COLUMNS: dict[str, dict[str, str]] = {
    "uploads": {
        "rights_review_id": "INTEGER",
        "quality_gate_status": "VARCHAR(40)",
        "metadata_json": "JSON",
    },
    "analytics": {
        "average_view_duration_seconds": "FLOAT",
        "average_view_percentage": "FLOAT",
        "watch_time_minutes": "FLOAT",
        "watch_percentage": "FLOAT",
        "subscriber_gain": "INTEGER",
        "shares": "INTEGER",
        "impressions": "INTEGER",
        "rewatch_rate": "FLOAT",
        "snapshot_window_hours": "INTEGER",
        "upload_age_hours": "FLOAT",
        "metric_source": "VARCHAR(20) NOT NULL DEFAULT 'REAL'",
        "capture_status": "VARCHAR(40) NOT NULL DEFAULT 'captured'",
        "unavailable_metrics": "JSON",
        "raw_json": "JSON",
        "error": "TEXT",
    },
}


def run_migrations(connection: Connection) -> None:
    """Run additive migrations for supported local databases."""

    if connection.dialect.name != "sqlite":
        return
    for table_name, columns in SQLITE_COLUMNS.items():
        existing = _sqlite_columns(connection, table_name)
        if not existing:
            continue
        for column_name, ddl in columns.items():
            if column_name not in existing:
                connection.exec_driver_sql(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {ddl}")


def _sqlite_columns(connection: Connection, table_name: str) -> set[str]:
    rows = connection.exec_driver_sql(f"PRAGMA table_info({table_name})").fetchall()
    return {str(row[1]) for row in rows}
