from fastapi import APIRouter

from app.api.routes import bookings, customers, dashboard, expenses, inventory, properties

api_router = APIRouter()
api_router.include_router(dashboard.router, prefix="/dashboard", tags=["dashboard"])
api_router.include_router(bookings.router, prefix="/bookings", tags=["bookings"])
api_router.include_router(customers.router, prefix="/customers", tags=["customers"])
api_router.include_router(inventory.router, prefix="/inventory", tags=["inventory"])
api_router.include_router(expenses.router, prefix="/expenses", tags=["expenses"])
api_router.include_router(properties.router, prefix="/properties", tags=["properties"])
