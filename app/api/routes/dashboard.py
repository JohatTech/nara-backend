from datetime import date

from fastapi import APIRouter, Depends

from app.core.auth import current_owner
from app.core.database import get_supabase
from app.services.dashboard import DashboardService

router = APIRouter()


@router.get("")
def get_dashboard(owner_id: str = Depends(current_owner)) -> dict:
    return DashboardService(get_supabase()).summary(owner_id, date.today())
