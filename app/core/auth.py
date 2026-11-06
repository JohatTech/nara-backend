from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
import jwt
import httpx
from jwt import PyJWKClient, PyJWTError

from app.core.config import settings

bearer = HTTPBearer(auto_error=False)
jwks_client = PyJWKClient(settings.supabase_jwks_url, cache_keys=True)


def current_owner(credentials: HTTPAuthorizationCredentials | None = Depends(bearer)) -> str:
    if credentials is None:
        raise HTTPException(status_code=401, detail="Authentication required")
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
                raise HTTPException(status_code=401, detail="Invalid access token")
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
        return str(owner_id)
    except httpx.HTTPStatusError as error:
        status_code = 503 if error.response.status_code >= 500 else 401
        detail = "Authentication service unavailable" if status_code == 503 else "Invalid access token"
        raise HTTPException(status_code=status_code, detail=detail) from None
    except httpx.HTTPError:
        raise HTTPException(status_code=503, detail="Authentication service unavailable") from None
    except (PyJWTError, ValueError):
        raise HTTPException(status_code=401, detail="Invalid access token") from None
