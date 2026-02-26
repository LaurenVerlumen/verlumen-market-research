#!/bin/bash
# Restore the SQLite database from the git-tracked backup.sql.
# Usage: bash scripts/restore_db.sh
# Run this after cloning the repo on a new machine.

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
DB_PATH="$PROJECT_DIR/data/verlumen.db"
BACKUP_PATH="$PROJECT_DIR/data/backup.sql"

if [ ! -f "$BACKUP_PATH" ]; then
    echo "ERROR: No backup found at $BACKUP_PATH"
    echo "Make sure you pulled the latest changes from git."
    exit 1
fi

if [ -f "$DB_PATH" ]; then
    echo "Database already exists at $DB_PATH"
    read -p "Overwrite with backup? (y/N) " -r
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo "Aborted."
        exit 0
    fi
    rm "$DB_PATH"
fi

mkdir -p "$(dirname "$DB_PATH")"
sqlite3 "$DB_PATH" < "$BACKUP_PATH"

if [ $? -eq 0 ]; then
    echo "Database restored successfully to $DB_PATH"
else
    echo "ERROR: Restore failed" >&2
    exit 1
fi
