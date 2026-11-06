from fastapi import APIRouter, Depends

from app.api.schemas import InventoryAdjustment, InventoryItemCreate
from app.core.auth import current_owner
from app.core.database import get_supabase

router = APIRouter()


@router.post("", status_code=201)
def create_inventory_item(payload: InventoryItemCreate, owner_id: str = Depends(current_owner)) -> dict:
    data = payload.model_dump(mode="json")
    data.update(owner_id=owner_id, currency=payload.currency.upper())
    return get_supabase().table("inventory_items").insert(data).execute().data[0]


@router.get("")
def list_inventory(owner_id: str = Depends(current_owner)) -> list[dict]:
    return (
        get_supabase().table("inventory_items").select("*, properties(name)")
        .eq("owner_id", owner_id).order("name").execute().data
    )


@router.post("/{item_id}/adjust")
def adjust_inventory(item_id: str, payload: InventoryAdjustment, owner_id: str = Depends(current_owner)) -> dict:
    result = get_supabase().rpc("adjust_inventory", {
        "p_owner_id": owner_id,
        "p_item_id": item_id,
        "p_quantity_delta": str(payload.quantity_delta),
        "p_unit_cost": str(payload.unit_cost),
        "p_note": payload.note,
    }).execute()
    if not result.data:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Inventory item not found or adjustment would make stock negative")
    return result.data
