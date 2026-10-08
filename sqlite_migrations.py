"""Backup-first SQLite migration for optional Beat Life Areas."""
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path


def migrate_nullable_beat_area(database_path):
    path = Path(database_path)
    if not path.exists():
        return False
    with sqlite3.connect(str(path)) as connection:
        table = connection.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='sum_entry'").fetchone()
        if not table:
            return False
        columns = connection.execute("PRAGMA table_info(sum_entry)").fetchall()
        if not any(col[1] == "life_area_id" and col[3] for col in columns):
            return False
        original = table[0]
        updated = re.sub(r'(\blife_area_id\b\s+[^,)]*?)\s+NOT\s+NULL\b', r'\1', original, count=1, flags=re.I)
        if updated == original:
            raise RuntimeError("Unable to identify life_area_id NOT NULL constraint")
        updated = re.sub(r'^CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?["\x60]?sum_entry["\x60]?', 'CREATE TABLE sum_entry_nullable_migration', updated, count=1, flags=re.I)
        if "sum_entry_nullable_migration" not in updated:
            raise RuntimeError("Unable to safely rebuild sum_entry table")
        backup_path = str(path) + ".pre_nullable_area_" + datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S%f") + ".bak"
        with sqlite3.connect(backup_path) as backup:
            connection.backup(backup)
        indexes = [row[0] for row in connection.execute("SELECT sql FROM sqlite_master WHERE type='index' AND tbl_name='sum_entry' AND sql IS NOT NULL")]
        names = ', '.join('"' + col[1].replace('"', '""') + '"' for col in columns)
        connection.execute("PRAGMA foreign_keys=OFF")
        try:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(updated)
            connection.execute(f"INSERT INTO sum_entry_nullable_migration ({names}) SELECT {names} FROM sum_entry")
            connection.execute("DROP TABLE sum_entry")
            connection.execute("ALTER TABLE sum_entry_nullable_migration RENAME TO sum_entry")
            for statement in indexes:
                connection.execute(statement)
            if connection.execute("PRAGMA foreign_key_check").fetchall():
                raise RuntimeError("Foreign key check failed")
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.execute("PRAGMA foreign_keys=ON")
    return True
