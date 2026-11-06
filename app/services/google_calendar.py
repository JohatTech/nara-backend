from __future__ import annotations

import base64
import json
import logging
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote, urlencode

import httpx
import jwt

from app.core.config import settings

logger = logging.getLogger(__name__)

GOOGLE_CALENDAR_SCOPE = "https://www.googleapis.com/auth/calendar"
GOOGLE_TOKEN_URI = "https://oauth2.googleapis.com/token"
GOOGLE_CALENDAR_API_BASE = "https://www.googleapis.com/calendar/v3"


def _extract_iframe_src(value: str) -> str:
    match = re.search(r"""src\s*=\s*["']([^"']+)["']""", value, re.IGNORECASE)
    if match:
        return match.group(1).replace("&amp;", "&").strip()
    return value.strip()


def build_embed_url(
    calendar_id: str | None = None,
    tz: str | None = None,
    mode: str = "MONTH",
) -> str:
    raw_embed = _extract_iframe_src(settings.google_calendar_embed_url)
    if raw_embed and not calendar_id:
        return raw_embed

    cal_id = _extract_iframe_src(calendar_id or settings.google_calendar_id)
    if not cal_id:
        return ""
    if cal_id.startswith("http://") or cal_id.startswith("https://"):
        return cal_id

    timezone_name = (tz or settings.google_calendar_timezone or "America/Panama").strip()
    params = {
        "src": cal_id,
        "ctz": timezone_name,
        "mode": mode,
        "showTitle": "0",
        "showNav": "1",
        "showDate": "1",
        "showPrint": "0",
        "showTabs": "1",
        "showCalendars": "0",
        "showTz": "1",
        "wkst": "1",
    }
    return f"https://calendar.google.com/calendar/embed?{urlencode(params)}"


def _resolve_calendar_id(calendar_id: str | None = None) -> str:
    candidates = [
        calendar_id or "",
        settings.google_calendar_id,
        settings.google_calendar_embed_url,
    ]
    for raw in candidates:
        extracted = _extract_iframe_src(raw)
        if not extracted:
            continue
        if not extracted.startswith("http://") and not extracted.startswith("https://"):
            return extracted
        m = re.search(r"[?&]src=([^&]+)", extracted)
        if m:
            from urllib.parse import unquote

            return unquote(m.group(1)).strip()
    return ""


def _load_service_account_info() -> dict | None:
    raw = settings.google_service_account_json.strip()
    if (
        (raw.startswith('"') and raw.endswith('"'))
        or (raw.startswith("'") and raw.endswith("'"))
    ):
        raw = raw[1:-1].strip()

    if raw:
        # 1. Direct JSON string (strict=False allows literal newlines from Render env vars)
        if raw.startswith("{"):
            for candidate in (raw, raw.replace('\\"', '"')):
                try:
                    return json.loads(candidate, strict=False)
                except json.JSONDecodeError:
                    pass
            logger.warning("Invalid JSON in GOOGLE_SERVICE_ACCOUNT_JSON")

        # 2. File path
        try:
            candidate_path = Path(raw)
            if candidate_path.is_file():
                return json.loads(
                    candidate_path.read_text(encoding="utf-8"), strict=False
                )
        except Exception as exc:
            logger.warning("Could not read GOOGLE_SERVICE_ACCOUNT_JSON file: %s", exc)

        # 3. Base64-encoded JSON
        try:
            decoded = base64.b64decode(raw).decode("utf-8")
            if decoded.strip().startswith("{"):
                return json.loads(decoded, strict=False)
        except Exception:
            pass

    # 4. Separate GOOGLE_CLIENT_EMAIL + GOOGLE_PRIVATE_KEY env vars
    if settings.google_client_email.strip() and settings.google_private_key.strip():
        return {
            "type": "service_account",
            "client_email": settings.google_client_email.strip(),
            "private_key": settings.google_private_key.strip(),
            "token_uri": GOOGLE_TOKEN_URI,
        }

    return None


def is_sync_configured(calendar_id: str | None = None) -> bool:
    return bool(_resolve_calendar_id(calendar_id) and _load_service_account_info())


def _get_access_token(sa_info: dict) -> str:
    now = int(time.time())
    token_uri = sa_info.get("token_uri", GOOGLE_TOKEN_URI)
    payload = {
        "iss": sa_info["client_email"],
        "scope": GOOGLE_CALENDAR_SCOPE,
        "aud": token_uri,
        "iat": now,
        "exp": now + 3600,
    }
    private_key = sa_info["private_key"].replace("\\n", "\n")
    assertion = jwt.encode(payload, private_key, algorithm="RS256")

    with httpx.Client(timeout=15.0) as client:
        response = client.post(
            token_uri,
            data={
                "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
                "assertion": assertion,
            },
        )
        response.raise_for_status()
        return response.json()["access_token"]


def _event_id_for_booking(booking_id: str) -> str:
    cleaned = re.sub(r"[^a-v0-9]", "", booking_id.lower())
    return f"nara{cleaned}"[:128]


def _build_event_payload(booking: dict) -> dict:
    guest_name = "Huésped"
    guest_email = None
    if isinstance(booking.get("customers"), dict):
        guest_name = booking["customers"].get("name") or guest_name
        guest_email = booking["customers"].get("email")

    property_name = "Propiedad"
    if isinstance(booking.get("properties"), dict):
        property_name = booking["properties"].get("name") or property_name

    status_raw = str(booking.get("status") or "confirmed").lower()
    gcal_status = "cancelled" if "cancel" in status_raw else "confirmed"

    check_in_str = str(booking.get("check_in") or "")
    check_out_str = str(booking.get("check_out") or "")
    check_in_date = check_in_str[:10]
    check_out_date = check_out_str[:10]

    currency = booking.get("currency") or "USD"
    total_amount = booking.get("total_amount") or "0"
    source = booking.get("source") or "Directa"
    notes = booking.get("notes") or ""

    description_lines = [
        f"Propiedad: {property_name}",
        f"Huésped: {guest_name}" + (f" ({guest_email})" if guest_email else ""),
        f"Monto Total: {currency} {total_amount}",
        f"Canal / Origen: {source}",
        f"Estado en Nara: {booking.get('status', 'confirmed')}",
    ]
    if notes:
        description_lines.append(f"Notas: {notes}")

    return {
        "id": _event_id_for_booking(str(booking["id"])),
        "summary": f"Reserva: {guest_name} · {property_name}",
        "description": "\n".join(description_lines),
        "status": gcal_status,
        "start": {"date": check_in_date},
        "end": {"date": check_out_date},
    }


def sync_booking_to_google_calendar(booking: dict, calendar_id: str | None = None) -> dict | None:
    target_calendar = _resolve_calendar_id(calendar_id)
    sa_info = _load_service_account_info()
    if not target_calendar or not sa_info:
        return None

    token = _get_access_token(sa_info)
    event_payload = _build_event_payload(booking)
    event_id = event_payload["id"]
    encoded_cal = quote(target_calendar, safe="")
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }

    with httpx.Client(timeout=15.0, headers=headers) as client:
        # Try update first if event already exists, otherwise insert
        put_url = f"{GOOGLE_CALENDAR_API_BASE}/calendars/{encoded_cal}/events/{event_id}"
        resp = client.put(put_url, json=event_payload)
        if resp.status_code == 404:
            post_url = f"{GOOGLE_CALENDAR_API_BASE}/calendars/{encoded_cal}/events"
            resp = client.post(post_url, json=event_payload)
        elif resp.status_code == 409:
            resp = client.put(put_url, json=event_payload)

        resp.raise_for_status()
        return resp.json()


def generate_ical_feed(bookings: list[dict]) -> str:
    now_str = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//Nara Boutique Reservations//ES",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        "X-WR-CALNAME:Nara · Reservas",
    ]
    for b in bookings:
        event = _build_event_payload(b)
        start_date = event["start"]["date"].replace("-", "")
        end_date = event["end"]["date"].replace("-", "")
        summary = event["summary"].replace("\n", " ")
        desc = event["description"].replace("\n", "\\n")
        uid = f"{b.get('id')}@nara.app"
        status = "CANCELLED" if event["status"] == "cancelled" else "CONFIRMED"
        lines.extend([
            "BEGIN:VEVENT",
            f"UID:{uid}",
            f"DTSTAMP:{now_str}",
            f"DTSTART;VALUE=DATE:{start_date}",
            f"DTEND;VALUE=DATE:{end_date}",
            f"SUMMARY:{summary}",
            f"DESCRIPTION:{desc}",
            f"STATUS:{status}",
            "END:VEVENT",
        ])
    lines.append("END:VCALENDAR")
    return "\r\n".join(lines) + "\r\n"

