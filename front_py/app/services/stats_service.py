from typing import Literal

import httpx

from app.core.config import settings


class StatsService:
    """ส่งออเดอร์ เงินเข้า และบิลที่เปิดอยู่ไปเก็บที่ Backend
    พร้อมดึงสถิติมาแสดงบนแดชบอร์ด

    หากเขียนข้อมูลไม่สำเร็จ จะคืน False เพื่อให้ลูกค้าใช้งานต่อได้
    """

    def __init__(self):
        self.backend_url = settings.BACKEND_URL

    # ---------- เขียนข้อมูล ----------

    async def _write(
        self,
        method: str,
        path: str,
        payload: dict,
    ) -> bool:
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.request(
                    method,
                    f"{self.backend_url}{path}",
                    json=payload,
                )
                resp.raise_for_status()
            return True
        except httpx.HTTPError as exc:
            print(f"[Stats] ส่งข้อมูลสถิติไม่สำเร็จ ({path}): {exc}")
            return False

    async def record_order(
        self,
        table: int | None,
        items: list[dict],
    ) -> bool:
        if not items:
            return False

        return await self._write(
            "POST",
            "/api/stats/orders",
            {
                "table": table,
                "items": items,
            },
        )

    async def record_transaction(
        self,
        table: int | None,
        method: str,
        amount: float,
        items: list[dict],
        bill_closed: bool,
    ) -> bool:
        return await self._write(
            "POST",
            "/api/stats/transactions",
            {
                "table": table,
                "method": method,
                "amount": amount,
                "items": items,
                "bill_closed": bill_closed,
            },
        )

    async def sync_live_order(
        self,
        table: int | None,
        items: list[dict],
        status: Literal["dining", "waiting_payment"] | None = None,
    ) -> bool:
        """อัปเดตบิลและสถานะโต๊ะ

        dining = กำลังรับประทาน
        waiting_payment = รอชำระ
        ไม่ส่ง status = รักษาสถานะเดิม หรือ dining สำหรับโต๊ะใหม่
        items ว่าง = โต๊ะว่าง ตามพฤติกรรมเดิม
        """
        if table is None:
            return False

        payload = {"items": items}

        if status is not None:
            payload["status"] = status

        return await self._write(
            "PUT",
            f"/api/stats/live-orders/{table}",
            payload,
        )

    # ---------- อ่านข้อมูล ----------

    async def get_dashboard(self) -> dict:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                f"{self.backend_url}/api/stats/dashboard"
            )
            resp.raise_for_status()
            return resp.json()

    async def set_availability(
        self,
        item_id: int,
        available: bool,
    ) -> bool:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                f"{self.backend_url}/api/stats/availability/{item_id}",
                json={"available": available},
            )

            if resp.status_code == 404:
                return False

            resp.raise_for_status()
            return True


async def build_lines(
    menu_service,
    quantities: dict,
) -> list[dict]:
    """แปลง {item_id: qty} เป็นรายการที่มีชื่อและราคา"""
    lines = []

    for item_id, qty in quantities.items():
        if int(qty) <= 0:
            continue

        menu_item = await menu_service.get_by_id(int(item_id))

        if menu_item:
            lines.append({
                "id": menu_item.id,
                "name": menu_item.name,
                "price": menu_item.price,
                "qty": int(qty),
            })

    return lines