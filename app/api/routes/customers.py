from fastapi import APIRouter, Depends

from app.api.schemas import CustomerCreate
from app.core.auth import current_owner
from app.core.database import get_supabase

router = APIRouter()


@router.get("")
def list_customers(owner_id: str = Depends(current_owner)) -> list[dict]:
    return get_supabase().table("customers").select("*").eq("owner_id", owner_id).order("name").execute().data


@router.post("", status_code=201)
def create_customer(payload: CustomerCreate, owner_id: str = Depends(current_owner)) -> dict:
    data = payload.model_dump()
    data["owner_id"] = owner_id
    return get_supabase().table("customers").insert(data).execute().data[0]
