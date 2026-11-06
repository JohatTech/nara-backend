from fastapi import APIRouter, Depends, HTTPException

from app.api.schemas import InventoryAdjustment, InventoryItemCreate, InventoryItemUpdate
from app.core.auth import current_owner
from app.core.database import get_supabase

router = APIRouter()


@router.post("", status_code=201)
def create_inventory_item(payload: InventoryItemCreate, owner_id: str = Depends(current_owner)) -> dict:
    db = get_supabase()
    effective_owner_id = owner_id
    prop = db.table("properties").select("owner_id").eq("id", payload.property_id).maybe_single().execute().data
    if prop and prop.get("owner_id"):
        effective_owner_id = str(prop["owner_id"])

    data = payload.model_dump(mode="json")
    data.update(owner_id=effective_owner_id, currency=payload.currency.upper())
    return db.table("inventory_items").insert(data).execute().data[0]


@router.get("")
def list_inventory(owner_id: str = Depends(current_owner)) -> list[dict]:
    return (
        get_supabase().table("inventory_items").select("*, properties(name)")
        .order("name").execute().data
    )


@router.put("/{item_id}")
def update_inventory_item(item_id: str, payload: InventoryItemUpdate, owner_id: str = Depends(current_owner)) -> dict:
    data = payload.model_dump(mode="json")
    data["currency"] = payload.currency.upper()
    result = get_supabase().table("inventory_items").update(data).eq("id", item_id).execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="Artículo de inventario no encontrado")
    return result.data[0]


@router.delete("/{item_id}")
def delete_inventory_item(item_id: str, owner_id: str = Depends(current_owner)) -> dict:
    result = get_supabase().table("inventory_items").delete().eq("id", item_id).execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="Artículo de inventario no encontrado")
    return {"deleted": True, "id": item_id}


@router.post("/{item_id}/adjust")
def adjust_inventory(item_id: str, payload: InventoryAdjustment, owner_id: str = Depends(current_owner)) -> dict:
    db = get_supabase()
    effective_owner_id = owner_id
    item = db.table("inventory_items").select("owner_id").eq("id", item_id).maybe_single().execute().data
    if item and item.get("owner_id"):
        effective_owner_id = str(item["owner_id"])

    result = db.rpc("adjust_inventory", {
        "p_owner_id": effective_owner_id,
        "p_item_id": item_id,
        "p_quantity_delta": str(payload.quantity_delta),
        "p_unit_cost": str(payload.unit_cost),
        "p_note": payload.note,
    }).execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="Artículo de inventario no encontrado o el ajuste dejaría el stock en negativo")
    return result.data
