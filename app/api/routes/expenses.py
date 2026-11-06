from fastapi import APIRouter, Depends

from app.api.schemas import ExpenseCreate
from app.core.auth import current_owner
from app.core.database import get_supabase

router = APIRouter()


@router.get("")
def list_expenses(owner_id: str = Depends(current_owner)) -> list[dict]:
    return get_supabase().table("expenses").select("*, properties(name)").eq("owner_id", owner_id).order("occurred_on", desc=True).execute().data


@router.post("", status_code=201)
def create_expense(payload: ExpenseCreate, owner_id: str = Depends(current_owner)) -> dict:
    data = payload.model_dump(mode="json")
    data.update(owner_id=owner_id, currency=payload.currency.upper())
    return get_supabase().table("expenses").insert(data).execute().data[0]
