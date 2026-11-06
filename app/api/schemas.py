from datetime import date
from decimal import Decimal

from pydantic import AwareDatetime, BaseModel, Field, field_validator


class CustomerCreate(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    email: str | None = Field(default=None, max_length=254)
    phone: str | None = Field(default=None, max_length=40)
    notes: str | None = Field(default=None, max_length=2000)


class CustomerUpdate(CustomerCreate):
    pass


class PropertyCreate(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    address: str | None = Field(default=None, max_length=500)
    currency: str = Field(default="USD", min_length=3, max_length=3)
    timezone: str = Field(default="America/Panama", max_length=80)


class PropertyUpdate(PropertyCreate):
    pass


class BookingCreate(BaseModel):
    property_id: str
    customer_id: str
    check_in: AwareDatetime
    check_out: AwareDatetime
    total_amount: Decimal = Field(ge=0, max_digits=12, decimal_places=2)
    currency: str = Field(min_length=3, max_length=3)
    source: str | None = Field(default=None, max_length=80)
    notes: str | None = Field(default=None, max_length=2000)


class BookingUpdate(BookingCreate):
    status: str = Field(default="confirmed", max_length=40)


class InventoryAdjustment(BaseModel):
    quantity_delta: Decimal = Field(max_digits=12, decimal_places=3)
    unit_cost: Decimal = Field(default=Decimal("0"), ge=0, max_digits=12, decimal_places=2)
    note: str | None = Field(default=None, max_length=500)

    @field_validator("quantity_delta")
    @classmethod
    def quantity_change_must_be_nonzero(cls, value: Decimal) -> Decimal:
        if value == 0:
            raise ValueError("Quantity change must be non-zero")
        return value


class InventoryItemCreate(BaseModel):
    property_id: str
    name: str = Field(min_length=1, max_length=160)
    category: str = Field(min_length=1, max_length=80)
    quantity: Decimal = Field(default=Decimal("0"), ge=0, max_digits=12, decimal_places=3)
    unit: str = Field(min_length=1, max_length=40)
    low_stock_threshold: Decimal = Field(default=Decimal("0"), ge=0, max_digits=12, decimal_places=3)
    unit_cost: Decimal = Field(default=Decimal("0"), ge=0, max_digits=12, decimal_places=2)
    currency: str = Field(min_length=3, max_length=3)


class InventoryItemUpdate(InventoryItemCreate):
    pass


class PaymentCreate(BaseModel):
    amount: Decimal = Field(gt=0, max_digits=12, decimal_places=2)
    currency: str = Field(min_length=3, max_length=3)
    received_at: AwareDatetime | None = None
    method: str | None = Field(default=None, max_length=80)
    note: str | None = Field(default=None, max_length=500)


class ExpenseCreate(BaseModel):
    property_id: str | None = None
    booking_id: str | None = None
    category: str = Field(min_length=1, max_length=80)
    description: str = Field(min_length=1, max_length=240)
    amount: Decimal = Field(gt=0, max_digits=12, decimal_places=2)
    currency: str = Field(min_length=3, max_length=3)
    occurred_on: date


class ExpenseUpdate(ExpenseCreate):
    pass
