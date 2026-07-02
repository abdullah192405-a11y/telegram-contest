import os
from functools import lru_cache

from supabase import Client, create_client

SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_SERVICE_ROLE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")


@lru_cache(maxsize=1)
def get_client() -> Client:
    if not SUPABASE_URL or not SUPABASE_SERVICE_ROLE_KEY:
        raise RuntimeError(
            "SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY must be set in .env"
        )
    return create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)


def init_db():
    get_client().table("participants").select("id").limit(1).execute()


def get_participant_by_username(username):
    response = (
        get_client()
        .table("participants")
        .select("*")
        .eq("telegram_username", username)
        .limit(1)
        .execute()
    )
    return response.data[0] if response.data else None


def get_participant_by_id(participant_id):
    response = (
        get_client()
        .table("participants")
        .select("*")
        .eq("id", participant_id)
        .limit(1)
        .execute()
    )
    return response.data[0] if response.data else None


def get_participant_by_link_name(link_name):
    response = (
        get_client()
        .table("participants")
        .select("*")
        .eq("link_name", link_name)
        .limit(1)
        .execute()
    )
    return response.data[0] if response.data else None


def insert_participant(name, username, password_hash, invite_link, link_name, created_at):
    response = (
        get_client()
        .table("participants")
        .insert(
            {
                "name": name,
                "telegram_username": username,
                "password_hash": password_hash,
                "invite_link": invite_link,
                "link_name": link_name,
                "joins_count": 0,
                "created_at": created_at.isoformat(),
            }
        )
        .execute()
    )
    return response.data[0]["id"]


def list_participants():
    response = (
        get_client()
        .table("participants")
        .select("*")
        .order("joins_count", desc=True)
        .order("created_at", desc=False)
        .execute()
    )
    return response.data


def get_leaderboard_rows():
    response = (
        get_client()
        .table("participants")
        .select("name, joins_count")
        .order("joins_count", desc=True)
        .order("created_at", desc=False)
        .limit(5)
        .execute()
    )
    return response.data


def get_participant_stats():
    response = (
        get_client()
        .table("participants")
        .select("joins_count", count="exact")
        .execute()
    )
    total_participants = response.count or 0
    total_joins = sum(row.get("joins_count", 0) for row in response.data)
    return total_participants, total_joins


def increment_join(participant_id, joined_name, joined_at):
    participant = get_participant_by_id(participant_id)
    if not participant:
        return

    client = get_client()
    client.table("participants").update(
        {"joins_count": participant["joins_count"] + 1}
    ).eq("id", participant_id).execute()
    client.table("joins_log").insert(
        {
            "participant_id": participant_id,
            "joined_user_name": joined_name,
            "joined_at": joined_at.isoformat(),
        }
    ).execute()
