#!/usr/bin/env python3
"""
Data Migration Script

This script migrates data from the old budtboy_preview.db to the new structure
"""
import sqlite3
import os
import shutil
from datetime import datetime


def migrate_database():
    """Migrate data from old database to new one"""

    old_db = 'budtboy_preview.db'
    new_db = 'budtboy_local.db'

    # Check if old database exists
    if not os.path.exists(old_db):
        print(f"❌ Old database {old_db} not found")
        print("Nothing to migrate")
        return

    # Backup old database
    backup_file = f"{old_db}.backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    shutil.copy2(old_db, backup_file)
    print(f"✅ Created backup: {backup_file}")

    # If new database doesn't exist, just copy the old one
    if not os.path.exists(new_db):
        shutil.copy2(old_db, new_db)
        print(f"✅ Copied {old_db} to {new_db}")
        print(f"✅ Migration completed successfully!")
        return

    # If both exist, merge data
    print("⚠️  Both databases exist. Merging data...")

    old_conn = sqlite3.connect(old_db)
    new_conn = sqlite3.connect(new_db)

    old_conn.row_factory = sqlite3.Row
    new_conn.row_factory = sqlite3.Row

    old_cur = old_conn.cursor()
    new_cur = new_conn.cursor()

    # Tables to migrate
    tables = [
        'users', 'admin_accounts', 'buds_data', 'reviews',
        'activities', 'activity_participants', 'friends',
        'email_verifications', 'password_resets',
        'strain_names', 'breeders', 'admin_settings', 'referrals'
    ]

    migrated_count = {}

    for table in tables:
        try:
            # Check if table exists in old database
            old_cur.execute(
                f"SELECT name FROM sqlite_master WHERE type='table' AND name=?",
                (table,)
            )
            if not old_cur.fetchone():
                print(f"⏭️  Table {table} not found in old database, skipping")
                continue

            # Get all data from old table
            old_cur.execute(f"SELECT * FROM {table}")
            rows = old_cur.fetchall()

            if not rows:
                print(f"⏭️  Table {table} is empty, skipping")
                continue

            count = 0
            for row in rows:
                # Convert row to dict
                data = dict(row)

                # Build insert query
                columns = ', '.join(data.keys())
                placeholders = ', '.join(['?' for _ in data])
                values = tuple(data.values())

                try:
                    new_cur.execute(
                        f"INSERT OR IGNORE INTO {table} ({columns}) VALUES ({placeholders})",
                        values
                    )
                    if new_cur.rowcount > 0:
                        count += 1
                except sqlite3.IntegrityError:
                    # Skip duplicates
                    pass

            migrated_count[table] = count
            print(f"✅ Migrated {count} rows from {table}")

        except Exception as e:
            print(f"❌ Error migrating {table}: {e}")

    # Commit changes
    new_conn.commit()

    # Close connections
    old_conn.close()
    new_conn.close()

    print("\n" + "=" * 60)
    print("📊 Migration Summary:")
    print("=" * 60)
    for table, count in migrated_count.items():
        print(f"  {table}: {count} rows")
    print("=" * 60)
    print("✅ Migration completed successfully!")
    print(f"✅ New database: {new_db}")
    print(f"✅ Backup saved: {backup_file}")


if __name__ == '__main__':
    print("=" * 60)
    print("🔄 BudtBoy Database Migration")
    print("=" * 60)
    print()

    migrate_database()
