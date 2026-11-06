from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
import jwt
import httpx
from jwt import PyJWKClient, PyJWTError

from app.core.config import settings
from app.core.database import get_supabase

bearer = HTTPBearer(auto_error=False)
jwks_client = PyJWKClient(settings.supabase_jwks_url, cache_keys=True)

_cached_workspace_owner_id: str | None = None


def _resolve_workspace_owner_id(authenticated_user_id: str) -> str:
    """
    Resolves the canonical workspace owner_id so all authenticated team members
    (e.g. Super Admin and Property Owner) share the same boutique properties,
    bookings, guests, expenses, and inventory.
    """
    global _cached_workspace_owner_id

    if settings.shared_owner_id.strip():
        return settings.shared_owner_id.strip()

    if _cached_workspace_owner_id:
        return _cached_workspace_owner_id

    try:
        db = get_supabase()
        for table in ("bookings", "properties", "customers", "expenses"):
            rows = (
                db.table(table)
                .select("owner_id")
                .order("created_at")
                .limit(1)
                .execute()
                .data
            )
            if rows and rows[0].get("owner_id"):
                _cached_workspace_owner_id = str(rows[0]["owner_id"])
                return _cached_workspace_owner_id
    except Exception:
        pass

    return authenticated_user_id


def current_owner(credentials: HTTPAuthorizationCredentials | None = Depends(bearer)) -> str:
    if credentials is None:
        raise HTTPException(status_code=401, detail="Autenticación requerida")
    try:
        token = credentials.credentials
        algorithm = jwt.get_unverified_header(token).get("alg")
        if algorithm == "HS256":
            # Legacy Supabase projects use a shared signing secret. Validate via Auth
            # rather than distributing that secret to this API.
            response = httpx.get(
                f"{settings.supabase_url.rstrip('/')}/auth/v1/user",
                headers={"apikey": settings.supabase_publishable_key, "Authorization": f"Bearer {token}"},
                timeout=5.0,
            )
            if response.status_code == 401:
                raise HTTPException(status_code=401, detail="Token de acceso no válido")
            response.raise_for_status()
            owner_id = response.json().get("id")
        elif algorithm in {"ES256", "RS256"}:
            signing_key = jwks_client.get_signing_key_from_jwt(token)
            claims = jwt.decode(
                token,
                signing_key.key,
                algorithms=[algorithm],
                audience="authenticated",
                issuer=f"{settings.supabase_url.rstrip('/')}/auth/v1",
            )
            owner_id = claims.get("sub")
        else:
            raise ValueError("Unsupported token algorithm")
        if not owner_id:
            raise ValueError("Missing subject")
        return _resolve_workspace_owner_id(str(owner_id))
    except httpx.HTTPStatusError as error:
        status_code = 503 if error.response.status_code >= 500 else 401
        detail = "Servicio de autenticación no disponible" if status_code == 503 else "Token de acceso no válido"
        raise HTTPException(status_code=status_code, detail=detail) from None
    except httpx.HTTPError:
        raise HTTPException(status_code=503, detail="Servicio de autenticación no disponible") from None
    except (PyJWTError, ValueError):
        raise HTTPException(status_code=401, detail="Token de acceso no válido") from None
