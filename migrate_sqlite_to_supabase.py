#!/usr/bin/env python3
"""One-time migration: copy data from local contest.db into Supabase.

Usage:
  source .venv/bin/activate
  set -a && source .env && set +a
  python3 migrate_sqlite_to_supabase.py
"""

import os
import sqlite3
import sys

from db import get_client, init_db

DB_PATH = os.path.join(os.path.dirname(__file__), "contest.db")


def main():
    if not os.path.isfile(DB_PATH):
        print(f"No SQLite file at {DB_PATH}")
        sys.exit(1)

    init_db()
    client = get_client()

    sqlite_conn = sqlite3.connect(DB_PATH)
    sqlite_conn.row_factory = sqlite3.Row

    participants = sqlite_conn.execute("SELECT * FROM participants").fetchall()
    joins = sqlite_conn.execute("SELECT * FROM joins_log").fetchall()
    sqlite_conn.close()

    for row in participants:
        client.table("participants").upsert(
            {
                "id": row["id"],
                "name": row["name"],
                "telegram_username": row["telegram_username"],
                "password_hash": row["password_hash"],
                "invite_link": row["invite_link"],
                "link_name": row["link_name"],
                "joins_count": row["joins_count"],
                "created_at": row["created_at"],
            }
        ).execute()

    for row in joins:
        client.table("joins_log").upsert(
            {
                "id": row["id"],
                "participant_id": row["participant_id"],
                "joined_user_name": row["joined_user_name"],
                "joined_at": row["joined_at"],
            }
        ).execute()

    print(f"Migrated {len(participants)} participants and {len(joins)} join log rows.")


if __name__ == "__main__":
    main()
