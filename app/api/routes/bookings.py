from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from postgrest.exceptions import APIError

from app.api.schemas import BookingCreate, PaymentCreate
from app.core.auth import current_owner
from app.core.database import get_supabase

router = APIRouter()


@router.post("", status_code=201)
def create_booking(payload: BookingCreate, owner_id: str = Depends(current_owner)) -> dict:
    if payload.check_out <= payload.check_in:
        raise HTTPException(status_code=422, detail="Check-out must be after check-in")
    data = payload.model_dump(mode="json")
    data.update(owner_id=owner_id, status="confirmed")
    try:
        return get_supabase().table("bookings").insert(data).execute().data[0]
    except APIError as error:
        if getattr(error, "code", None) == "23P01":
            raise HTTPException(status_code=409, detail="This property is already booked for those dates") from None
        raise HTTPException(status_code=400, detail="Booking could not be saved") from None


@router.get("")
def list_bookings(
    from_date: date | None = Query(default=None, alias="from"),
    to_date: date | None = Query(default=None, alias="to"),
    owner_id: str = Depends(current_owner),
) -> list[dict]:
    query = get_supabase().table("bookings").select("*, customers(name, email), properties(name)").eq("owner_id", owner_id)
    if from_date:
        query = query.gte("check_in", from_date.isoformat())
    if to_date:
        query = query.lte("check_out", to_date.isoformat())
    return query.order("check_in").execute().data


@router.get("/{booking_id}")
def get_booking(booking_id: str, owner_id: str = Depends(current_owner)) -> dict:
    result = get_supabase().table("bookings").select("*").eq("id", booking_id).eq("owner_id", owner_id).maybe_single().execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="Booking not found")
    return result.data


@router.post("/{booking_id}/payments", status_code=201)
def record_payment(booking_id: str, payload: PaymentCreate, owner_id: str = Depends(current_owner)) -> dict:
    result = get_supabase().rpc("record_payment", {
        "p_owner_id": owner_id,
        "p_booking_id": booking_id,
        "p_amount": str(payload.amount),
        "p_currency": payload.currency.upper(),
        "p_received_at": payload.received_at.isoformat() if payload.received_at else None,
        "p_method": payload.method,
        "p_note": payload.note,
    }).execute()
    if not result.data:
        raise HTTPException(status_code=409, detail="Payment could not be recorded; check the booking, currency, and remaining balance")
    return result.data
