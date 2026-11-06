from fastapi import APIRouter, Depends, HTTPException

from app.api.schemas import PropertyCreate, PropertyUpdate
from app.core.auth import current_owner
from app.core.database import get_supabase

router = APIRouter()


@router.get("")
def list_properties(owner_id: str = Depends(current_owner)) -> list[dict]:
    return get_supabase().table("properties").select("*").order("name").execute().data


@router.post("", status_code=201)
def create_property(payload: PropertyCreate, owner_id: str = Depends(current_owner)) -> dict:
    data = payload.model_dump()
    data.update(owner_id=owner_id, currency=payload.currency.upper())
    return get_supabase().table("properties").insert(data).execute().data[0]


@router.put("/{property_id}")
def update_property(property_id: str, payload: PropertyUpdate, owner_id: str = Depends(current_owner)) -> dict:
    data = payload.model_dump()
    data["currency"] = payload.currency.upper()
    result = get_supabase().table("properties").update(data).eq("id", property_id).execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="Propiedad no encontrada")
    return result.data[0]


@router.delete("/{property_id}")
def delete_property(property_id: str, owner_id: str = Depends(current_owner)) -> dict:
    db = get_supabase()
    result = db.table("properties").delete().eq("id", property_id).execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="Propiedad no encontrada")
    return {"deleted": True, "id": property_id}
