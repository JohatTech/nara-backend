from fastapi import APIRouter, Depends, HTTPException

from app.api.schemas import CustomerCreate, CustomerUpdate
from app.core.auth import current_owner
from app.core.database import get_supabase

router = APIRouter()


@router.get("")
def list_customers(owner_id: str = Depends(current_owner)) -> list[dict]:
    return get_supabase().table("customers").select("*").order("name").execute().data


@router.post("", status_code=201)
def create_customer(payload: CustomerCreate, owner_id: str = Depends(current_owner)) -> dict:
    data = payload.model_dump()
    data["owner_id"] = owner_id
    return get_supabase().table("customers").insert(data).execute().data[0]


@router.put("/{customer_id}")
def update_customer(customer_id: str, payload: CustomerUpdate, owner_id: str = Depends(current_owner)) -> dict:
    data = payload.model_dump()
    result = get_supabase().table("customers").update(data).eq("id", customer_id).execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="Huésped no encontrado")
    return result.data[0]


@router.delete("/{customer_id}")
def delete_customer(customer_id: str, owner_id: str = Depends(current_owner)) -> dict:
    result = get_supabase().table("customers").delete().eq("id", customer_id).execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="Huésped no encontrado")
    return {"deleted": True, "id": customer_id}
