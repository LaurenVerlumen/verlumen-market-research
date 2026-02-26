"""Database backup and restore utilities.

Keeps the SQLite data safe with:
- SQL text dump (git-trackable) at data/backup.sql
- Timestamped rolling backups in data/backups/
- Auto-backup on app startup and shutdown
- Periodic auto-backup every 30 minutes
- One-click git sync from the UI
- Restore from backup.sql when DB is missing
"""
import logging
import os
import shutil
import sqlite3
import subprocess
from datetime import datetime
from pathlib import Path

from config import DB_PATH, DATA_DIR

logger = logging.getLogger(__name__)

BACKUP_SQL = DATA_DIR / "backup.sql"
BACKUPS_DIR = DATA_DIR / "backups"
MAX_ROLLING_BACKUPS = 5

# Track last backup time for UI display
_last_backup_time: datetime | None = None


def backup_to_sql() -> Path | None:
    """Dump the database to a plain-text SQL file (git-friendly)."""
    global _last_backup_time
    if not DB_PATH.exists():
        return None
    try:
        BACKUP_SQL.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(DB_PATH))
        with open(BACKUP_SQL, "w", encoding="utf-8") as f:
            for line in conn.iterdump():
                f.write(f"{line}\n")
        conn.close()
        _last_backup_time = datetime.now()
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


def shutdown_backup():
    """Run on app shutdown: create a fresh backup."""
    logger.info("App shutting down — running backup...")
    if DB_PATH.exists():
        backup_to_sql()
        backup_rolling()
    logger.info("Shutdown backup complete.")


def get_last_backup_time() -> datetime | None:
    """Return the timestamp of the last successful SQL backup."""
    return _last_backup_time


def get_git_sync_status() -> dict:
    """Check if backup.sql has uncommitted changes or unpushed commits.

    Returns dict with keys: needs_commit, needs_push, last_commit_msg, error
    """
    project_dir = str(DATA_DIR.parent)
    result = {"needs_commit": False, "needs_push": False, "last_commit_msg": "", "error": None}
    try:
        # Check if backup.sql has uncommitted changes
        diff = subprocess.run(
            ["git", "diff", "--name-only", "data/backup.sql"],
            capture_output=True, text=True, cwd=project_dir, timeout=10,
        )
        staged = subprocess.run(
            ["git", "diff", "--cached", "--name-only", "data/backup.sql"],
            capture_output=True, text=True, cwd=project_dir, timeout=10,
        )
        result["needs_commit"] = bool(diff.stdout.strip() or staged.stdout.strip())

        # Check if ahead of remote
        status = subprocess.run(
            ["git", "status", "--porcelain", "--branch"],
            capture_output=True, text=True, cwd=project_dir, timeout=10,
        )
        result["needs_push"] = "ahead" in status.stdout

        # Last commit message
        log = subprocess.run(
            ["git", "log", "-1", "--format=%s", "--", "data/backup.sql"],
            capture_output=True, text=True, cwd=project_dir, timeout=10,
        )
        result["last_commit_msg"] = log.stdout.strip()
    except Exception as e:
        result["error"] = str(e)
    return result


def sync_to_git() -> dict:
    """Backup DB, commit backup.sql, and push to remote.

    Returns dict with keys: success, message
    """
    project_dir = str(DATA_DIR.parent)
    try:
        # 1. Fresh SQL dump
        backup_to_sql()

        # 2. Stage backup.sql
        subprocess.run(
            ["git", "add", "data/backup.sql"],
            capture_output=True, text=True, cwd=project_dir, timeout=10,
            check=True,
        )

        # 3. Check if there's anything to commit
        status = subprocess.run(
            ["git", "diff", "--cached", "--name-only"],
            capture_output=True, text=True, cwd=project_dir, timeout=10,
        )
        if not status.stdout.strip():
            return {"success": True, "message": "Already up to date — nothing to sync."}

        # 4. Commit
        stamp = datetime.now().strftime("%Y-%m-%d %H:%M")
        subprocess.run(
            ["git", "commit", "-m", f"Data sync {stamp}"],
            capture_output=True, text=True, cwd=project_dir, timeout=30,
            check=True,
        )

        # 5. Push
        push = subprocess.run(
            ["git", "push"],
            capture_output=True, text=True, cwd=project_dir, timeout=60,
        )
        if push.returncode != 0:
            return {"success": False, "message": f"Committed but push failed: {push.stderr.strip()}"}

        logger.info("Git sync complete: backup committed and pushed")
        return {"success": True, "message": f"Synced to git at {stamp}"}
    except subprocess.CalledProcessError as e:
        return {"success": False, "message": f"Git error: {e.stderr.strip() if e.stderr else str(e)}"}
    except Exception as e:
        return {"success": False, "message": str(e)}


def _prune_old_backups():
    """Keep only the most recent MAX_ROLLING_BACKUPS files."""
    backups = sorted(BACKUPS_DIR.glob("verlumen_*.db"), reverse=True)
    for old in backups[MAX_ROLLING_BACKUPS:]:
        try:
            old.unlink()
            logger.info("Pruned old backup: %s", old.name)
        except OSError:
            pass
