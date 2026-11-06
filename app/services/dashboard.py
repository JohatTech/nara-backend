from datetime import date, datetime, timezone
from decimal import Decimal

from supabase import Client


class DashboardService:
    """Centralizes money and inventory calculations on the trusted backend."""

    def __init__(self, db: Client) -> None:
        self.db = db

    def summary(self, owner_id: str, today: date) -> dict:
        month_start = today.replace(day=1)
        month_end = date(month_start.year + (month_start.month == 12), month_start.month % 12 + 1, 1)
        start = datetime.combine(month_start, datetime.min.time(), tzinfo=timezone.utc).isoformat()
        end = datetime.combine(month_end, datetime.min.time(), tzinfo=timezone.utc).isoformat()
        bookings = (
            self.db.table("bookings").select("id,status").eq("owner_id", owner_id)
            .gte("check_in", start).lt("check_in", end).execute().data
        )
        active = [b for b in bookings if b["status"] != "cancelled"]
        payments = self.db.table("payments").select("amount,currency").eq("owner_id", owner_id).gte("received_at", start).lt("received_at", end).execute().data
        expenses = self.db.table("expenses").select("amount,currency").eq("owner_id", owner_id).gte("occurred_on", month_start.isoformat()).lt("occurred_on", month_end.isoformat()).execute().data
        gross_by_currency = self._totals(payments)
        expenses_by_currency = self._totals(expenses)
        currencies = gross_by_currency.keys() | expenses_by_currency.keys()
        net_by_currency = {currency: gross_by_currency.get(currency, Decimal("0")) - expenses_by_currency.get(currency, Decimal("0")) for currency in currencies}
        now = datetime.now(timezone.utc).isoformat()
        upcoming = (
            self.db.table("bookings")
            .select("id,check_in,check_out,status,total_amount,currency,customers(name),properties(name)")
            .eq("owner_id", owner_id)
            .neq("status", "cancelled")
            .gte("check_in", now)
            .order("check_in")
            .execute()
            .data
        )
        inventory = (
            self.db.table("inventory_items")
            .select("quantity,low_stock_threshold")
            .eq("owner_id", owner_id)
            .execute()
            .data
        )
        low_stock_count = sum(
            Decimal(str(item["quantity"])) <= Decimal(str(item["low_stock_threshold"]))
            for item in inventory
        )
        return {
            "month": today.strftime("%Y-%m"),
            "gross_earnings_by_currency": {key: str(value) for key, value in gross_by_currency.items()},
            "expenses_by_currency": {key: str(value) for key, value in expenses_by_currency.items()},
            "net_earnings_by_currency": {key: str(value) for key, value in net_by_currency.items()},
            "booking_count": len(active),
            "upcoming_booking_count": len(upcoming),
            "next_bookings": upcoming[:3],
            "low_stock_count": low_stock_count,
        }

    @staticmethod
    def _totals(rows: list[dict]) -> dict[str, Decimal]:
        totals: dict[str, Decimal] = {}
        for row in rows:
            currency = row["currency"].strip()
            totals[currency] = totals.get(currency, Decimal("0")) + Decimal(str(row["amount"]))
        return totals
