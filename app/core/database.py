from functools import lru_cache

from supabase import Client, create_client

from app.core.config import settings


@lru_cache
def get_supabase() -> Client:
    # Secret key stays in the backend; routes must always scope queries by current_owner.
    return create_client(settings.supabase_url, settings.supabase_secret_key)
