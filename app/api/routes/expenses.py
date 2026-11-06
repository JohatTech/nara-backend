from fastapi import APIRouter, Depends

from app.api.schemas import ExpenseCreate
from app.core.auth import current_owner
from app.core.database import get_supabase

router = APIRouter()


@router.get("")
def list_expenses(owner_id: str = Depends(current_owner)) -> list[dict]:
    return get_supabase().table("expenses").select("*, properties(name)").order("occurred_on", desc=True).execute().data


@router.post("", status_code=201)
def create_expense(payload: ExpenseCreate, owner_id: str = Depends(current_owner)) -> dict:
    db = get_supabase()
    effective_owner_id = owner_id
    if payload.property_id:
        prop = db.table("properties").select("owner_id").eq("id", payload.property_id).maybe_single().execute().data
        if prop and prop.get("owner_id"):
            effective_owner_id = str(prop["owner_id"])
    elif payload.booking_id:
        bk = db.table("bookings").select("owner_id").eq("id", payload.booking_id).maybe_single().execute().data
        if bk and bk.get("owner_id"):
            effective_owner_id = str(bk["owner_id"])

    data = payload.model_dump(mode="json")
    data.update(owner_id=effective_owner_id, currency=payload.currency.upper())
    return db.table("expenses").insert(data).execute().data[0]
