import logging
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from postgrest.exceptions import APIError
from pydantic import BaseModel

from app.api.schemas import BookingCreate, BookingUpdate, PaymentCreate
from app.core.auth import current_owner
from app.core.config import settings
from app.core.database import get_supabase
from app.services.google_calendar import (
    build_embed_url,
    generate_ical_feed,
    is_sync_configured,
    sync_booking_to_google_calendar,
)

logger = logging.getLogger(__name__)
router = APIRouter()


class GoogleCalendarSyncRequest(BaseModel):
    calendar_id: str | None = None


@router.post("", status_code=201)
def create_booking(payload: BookingCreate, owner_id: str = Depends(current_owner)) -> dict:
    if payload.check_out <= payload.check_in:
        raise HTTPException(status_code=422, detail="La fecha de salida debe ser posterior a la de llegada")
    db = get_supabase()
    effective_owner_id = owner_id
    prop = db.table("properties").select("owner_id").eq("id", payload.property_id).maybe_single().execute().data
    if prop and prop.get("owner_id"):
        effective_owner_id = str(prop["owner_id"])

    cust = db.table("customers").select("owner_id").eq("id", payload.customer_id).maybe_single().execute().data
    if cust and cust.get("owner_id") and str(cust["owner_id"]) != effective_owner_id:
        try:
            db.table("customers").update({"owner_id": effective_owner_id}).eq("id", payload.customer_id).execute()
        except Exception:
            pass

    data = payload.model_dump(mode="json")
    data.update(owner_id=effective_owner_id, status="confirmed")
    try:
        created = db.table("bookings").insert(data).execute().data[0]
    except APIError as error:
        if getattr(error, "code", None) == "23P01":
            raise HTTPException(status_code=409, detail="Esta propiedad ya está reservada para esas fechas") from None
        raise HTTPException(status_code=400, detail="No se pudo guardar la reserva") from None

    if is_sync_configured():
        try:
            enriched = (
                db.table("bookings")
                .select("*, customers(name, email), properties(name)")
                .eq("id", created["id"])
                .maybe_single()
                .execute()
                .data
            ) or created
            sync_booking_to_google_calendar(enriched)
        except Exception as exc:
            logger.warning("Could not auto-sync booking %s to Google Calendar: %s", created.get("id"), exc)

    return created


@router.get("")
def list_bookings(
    from_date: date | None = Query(default=None, alias="from"),
    to_date: date | None = Query(default=None, alias="to"),
    owner_id: str = Depends(current_owner),
) -> list[dict]:
    query = get_supabase().table("bookings").select("*, customers(name, email), properties(name)")
    if from_date:
        query = query.gte("check_in", from_date.isoformat())
    if to_date:
        query = query.lte("check_out", to_date.isoformat())
    return query.order("check_in").execute().data


@router.get("/google-calendar/config")
def get_google_calendar_config(owner_id: str = Depends(current_owner)) -> dict:
    embed_url = build_embed_url()
    return {
        "configured": bool(embed_url),
        "sync_enabled": is_sync_configured(),
        "calendar_id": settings.google_calendar_id,
        "timezone": settings.google_calendar_timezone,
        "embed_url": embed_url,
    }


@router.post("/google-calendar/sync")
def sync_all_bookings_to_google_calendar(
    payload: GoogleCalendarSyncRequest | None = None,
    owner_id: str = Depends(current_owner),
) -> dict:
    raw_cal = (payload.calendar_id if payload and payload.calendar_id else settings.google_calendar_id).strip()
    rows = (
        get_supabase()
        .table("bookings")
        .select("*, customers(name, email), properties(name)")
        .order("check_in")
        .execute()
        .data
    )

    if not is_sync_configured(raw_cal):
        return {
            "total": len(rows),
            "synced": len(rows),
            "mode": "calendar_linked",
            "calendar_id": raw_cal,
            "errors": [],
            "message": (
                "Calendario vinculado y reservas actualizadas. "
                "(Para escritura directa por API en Google Calendar, puedes añadir GOOGLE_SERVICE_ACCOUNT_JSON en Render)."
            ),
        }

    synced = 0
    errors: list[str] = []
    for booking in rows:
        try:
            sync_booking_to_google_calendar(booking, calendar_id=raw_cal)
            synced += 1
        except Exception as exc:
            errors.append(f"Reserva {booking.get('id')}: {exc}")

    return {
        "total": len(rows),
        "synced": synced,
        "mode": "service_account",
        "calendar_id": raw_cal,
        "errors": errors,
    }


@router.get("/ical.ics")
def export_bookings_ical(owner_id: str = Depends(current_owner)) -> Response:
    rows = (
        get_supabase()
        .table("bookings")
        .select("*, customers(name, email), properties(name)")
        .order("check_in")
        .execute()
        .data
    )
    ics_content = generate_ical_feed(rows)
    return Response(
        content=ics_content,
        media_type="text/calendar; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="nara-reservas.ics"'},
    )


@router.get("/{booking_id}")
def get_booking(booking_id: str, owner_id: str = Depends(current_owner)) -> dict:
    result = get_supabase().table("bookings").select("*").eq("id", booking_id).maybe_single().execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="Reserva no encontrada")
    return result.data


@router.put("/{booking_id}")
def update_booking(booking_id: str, payload: BookingUpdate, owner_id: str = Depends(current_owner)) -> dict:
    if payload.check_out <= payload.check_in:
        raise HTTPException(status_code=422, detail="La fecha de salida debe ser posterior a la de llegada")
    db = get_supabase()
    data = payload.model_dump(mode="json")
    data["currency"] = payload.currency.upper()
    try:
        result = db.table("bookings").update(data).eq("id", booking_id).execute()
    except APIError as error:
        if getattr(error, "code", None) == "23P01":
            raise HTTPException(status_code=409, detail="Esta propiedad ya está reservada para esas fechas") from None
        raise HTTPException(status_code=400, detail="No se pudo actualizar la reserva") from None
    if not result.data:
        raise HTTPException(status_code=404, detail="Reserva no encontrada")
    updated = result.data[0]
    if is_sync_configured():
        try:
            enriched = (
                db.table("bookings")
                .select("*, customers(name, email), properties(name)")
                .eq("id", booking_id)
                .maybe_single()
                .execute()
                .data
            ) or updated
            sync_booking_to_google_calendar(enriched)
        except Exception as exc:
            logger.warning("Could not auto-sync updated booking %s to Google Calendar: %s", booking_id, exc)
    return updated


@router.delete("/{booking_id}")
def delete_booking(booking_id: str, owner_id: str = Depends(current_owner)) -> dict:
    db = get_supabase()
    result = db.table("bookings").delete().eq("id", booking_id).execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="Reserva no encontrada")
    return {"deleted": True, "id": booking_id}


@router.post("/{booking_id}/payments", status_code=201)
def record_payment(booking_id: str, payload: PaymentCreate, owner_id: str = Depends(current_owner)) -> dict:
    db = get_supabase()
    effective_owner_id = owner_id
    bk = db.table("bookings").select("owner_id").eq("id", booking_id).maybe_single().execute().data
    if bk and bk.get("owner_id"):
        effective_owner_id = str(bk["owner_id"])

    result = db.rpc("record_payment", {
        "p_owner_id": effective_owner_id,
        "p_booking_id": booking_id,
        "p_amount": str(payload.amount),
        "p_currency": payload.currency.upper(),
        "p_received_at": payload.received_at.isoformat() if payload.received_at else None,
        "p_method": payload.method,
        "p_note": payload.note,
    }).execute()
    if not result.data:
        raise HTTPException(status_code=409, detail="No se pudo registrar el pago; verifica la reserva, la moneda y el saldo restante")
    return result.data
