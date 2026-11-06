from fastapi import APIRouter, Depends

from app.api.schemas import PropertyCreate
from app.core.auth import current_owner
from app.core.database import get_supabase

router = APIRouter()


@router.get("")
def list_properties(owner_id: str = Depends(current_owner)) -> list[dict]:
    return get_supabase().table("properties").select("*").eq("owner_id", owner_id).order("name").execute().data


@router.post("", status_code=201)
def create_property(payload: PropertyCreate, owner_id: str = Depends(current_owner)) -> dict:
    data = payload.model_dump()
    data.update(owner_id=owner_id, currency=payload.currency.upper())
    return get_supabase().table("properties").insert(data).execute().data[0]
