"""Database backup and restore utilities.

Keeps the SQLite data safe with:
- SQL text dump (git-trackable) at data/backup.sql
- Timestamped rolling backups in data/backups/
- Auto-backup on app startup
- Restore from backup.sql when DB is missing
"""
import logging
import shutil
import sqlite3
from datetime import datetime
from pathlib import Path

from config import DB_PATH, DATA_DIR

logger = logging.getLogger(__name__)

BACKUP_SQL = DATA_DIR / "backup.sql"
BACKUPS_DIR = DATA_DIR / "backups"
MAX_ROLLING_BACKUPS = 5


def backup_to_sql() -> Path | None:
    """Dump the database to a plain-text SQL file (git-friendly)."""
    if not DB_PATH.exists():
        return None
    try:
        BACKUP_SQL.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(DB_PATH))
        with open(BACKUP_SQL, "w", encoding="utf-8") as f:
            for line in conn.iterdump():
                f.write(f"{line}\n")
        conn.close()
        logger.info("SQL backup written to %s", BACKUP_SQL)
        return BACKUP_SQL
    except Exception as e:
        logger.error("SQL backup failed: %s", e)
        return None


def backup_rolling() -> Path | None:
    """Create a timestamped copy of the DB file (rolling, keeps last N)."""
    if not DB_PATH.exists():
        return None
    try:
        BACKUPS_DIR.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        dest = BACKUPS_DIR / f"verlumen_{stamp}.db"
        shutil.copy2(str(DB_PATH), str(dest))
        logger.info("Rolling backup: %s", dest)
        _prune_old_backups()
        return dest
    except Exception as e:
        logger.error("Rolling backup failed: %s", e)
        return None


def restore_from_sql() -> bool:
    """Restore the database from backup.sql (used when DB is missing)."""
    if not BACKUP_SQL.exists():
        logger.warning("No backup.sql found — cannot restore.")
        return False
    if DB_PATH.exists():
        logger.info("Database already exists — skipping restore.")
        return False
    try:
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(DB_PATH))
        with open(BACKUP_SQL, "r", encoding="utf-8") as f:
            conn.executescript(f.read())
        conn.close()
        logger.info("Database restored from %s", BACKUP_SQL)
        return True
    except Exception as e:
        logger.error("Restore failed: %s", e)
        return False


def startup_backup():
    """Run on app startup: restore if needed, then backup."""
    if not DB_PATH.exists() and BACKUP_SQL.exists():
        logger.info("Database missing — restoring from backup.sql...")
        restore_from_sql()

    if DB_PATH.exists():
        backup_to_sql()
        backup_rolling()


def _prune_old_backups():
    """Keep only the most recent MAX_ROLLING_BACKUPS files."""
    backups = sorted(BACKUPS_DIR.glob("verlumen_*.db"), reverse=True)
    for old in backups[MAX_ROLLING_BACKUPS:]:
        try:
            old.unlink()
            logger.info("Pruned old backup: %s", old.name)
        except OSError:
            pass
