#!/bin/bash
# Dump SQLite database to a sorted SQL text file for git tracking.
# Uses Python backup_to_sql() for deterministic (sorted) output so
# identical data always produces the same file (no false git diffs).
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

# Use the Python sorted backup (deterministic output, no false diffs)
cd "$PROJECT_DIR"
if [ -f "venv/Scripts/python.exe" ]; then
    PYTHON="venv/Scripts/python.exe"
elif [ -f "venv/bin/python" ]; then
    PYTHON="venv/bin/python"
else
    PYTHON="python"
fi

$PYTHON -c "from src.services.db_backup import backup_to_sql; backup_to_sql()"

if [ $? -eq 0 ]; then
    echo "Database backed up to $BACKUP_PATH"
    git add "$BACKUP_PATH" 2>/dev/null
else
    echo "WARNING: Database backup failed" >&2
    exit 1
fi
