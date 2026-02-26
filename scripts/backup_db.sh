#!/bin/bash
# Dump SQLite database to a text SQL file for git tracking.
# Usage: bash scripts/backup_db.sh
# Called automatically by the pre-commit hook.

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
DB_PATH="$PROJECT_DIR/data/verlumen.db"
BACKUP_PATH="$PROJECT_DIR/data/backup.sql"

if [ ! -f "$DB_PATH" ]; then
    echo "No database found at $DB_PATH — skipping backup."
    exit 0
fi

sqlite3 "$DB_PATH" .dump > "$BACKUP_PATH"

if [ $? -eq 0 ]; then
    echo "Database backed up to $BACKUP_PATH"
    git add "$BACKUP_PATH" 2>/dev/null
else
    echo "WARNING: Database backup failed" >&2
    exit 1
fi
