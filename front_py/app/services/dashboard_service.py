"""Frontend client for order, payment, and dashboard data stored by Firestore."""

import httpx

from app.core.config import settings


class DashboardService:
    def __init__(self):
        self.backend_url = settings.BACKEND_URL

    async def _request(self, method: str, path: str, payload: dict | None = None):
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.request(
                method, f"{self.backend_url}{path}", json=payload
            )
            response.raise_for_status()
            return response.json() if response.content else {}

    async def place_order(self, table: int, items: list[dict]):
        return await self._request("POST", "/api/stats/orders", {"table": table, "items": items})

    async def dashboard_data(self):
        return await self._request("GET", "/api/stats/dashboard")

    async def set_table_status(self, table: int, status: str):
        return await self._request("PUT", f"/api/stats/live-orders/{table}/status", {"status": status})

    async def record_payment(self, table: int, method: str):
        return await self._request("POST", f"/api/stats/live-orders/{table}/pay", {"method": method})

    async def reset_table(self, table: int):
        return await self._request("POST", f"/api/stats/live-orders/{table}/reset")

    async def set_kitchen_status(self, table: int, item_id: int, status: str):
        return await self._request(
            "PUT",
            f"/api/stats/live-orders/{table}/items/{item_id}/kitchen",
            {"status": status},
        )
