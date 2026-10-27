from typing import Literal

import httpx

from app.core.admin_auth import admin_api_key
from app.core.config import settings


class StatsService:
    """ติดต่อ Backend สำหรับออเดอร์ สถิติ และการชำระเงิน"""

    def __init__(self):
        self.backend_url = settings.BACKEND_URL

    # ---------- ส่งข้อมูลทั่วไป ----------

    async def _write(
        self,
        method: str,
        path: str,
        payload: dict,
    ) -> bool:
        """คืน False เมื่อส่งข้อมูลไม่สำเร็จ"""
        try:
            async with httpx.AsyncClient(
                timeout=5.0
            ) as client:
                response = await client.request(
                    method,
                    f"{self.backend_url}{path}",
                    json=payload,
                    headers={
                        "X-Food-Kub-Key": admin_api_key(),
                    },
                )

                response.raise_for_status()

            return True

        except httpx.HTTPError as exc:
            print(
                f"[Stats] ส่งข้อมูลไม่สำเร็จ "
                f"({path}): {exc}"
            )
            return False

    # ---------- บันทึกออเดอร์ ----------

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

    # ---------- บันทึกการชำระเงิน ----------

    async def record_transaction(
        self,
        table: int | None,
        method: str,
        amount: float,
        items: list[dict],
        bill_closed: bool,
        payment_type: Literal["full", "split"] | None = None,
    ) -> bool:
        """
        full = ชำระทั้งบิล
        split = แยกจ่าย
        bill_closed = รายการนี้ทำให้บิลชำระครบหรือไม่
        """
        return await self._write(
            "POST",
            "/api/stats/transactions",
            {
                "table": table,
                "method": method,
                "amount": amount,
                "items": items,
                "bill_closed": bill_closed,
                "payment_type": payment_type,
            },
        )

    # ---------- อัปเดตบิลและสถานะโต๊ะ ----------

    async def sync_live_order(
        self,
        table: int | None,
        items: list[dict],
        status: Literal[
            "dining",
            "waiting_payment",
        ] | None = None,
        shared_paid: float = 0,
        shared_item_ids: list[int] | None = None,
        expected_opened_at: str | None = None,
        expected_updated_at: str | None = None,
    ) -> bool:
        """
        dining = กำลังรับประทาน
        waiting_payment = รอชำระ

        ส่งเวลาของบิลที่อ่านมาให้ Backend ตรวจสอบ
        เพื่อป้องกันเขียนทับบิลที่เปลี่ยนไป
        """
        if table is None:
            return False

        payload = {
            "items": items,
            "shared_paid": shared_paid,
            "expected_opened_at": expected_opened_at,
            "expected_updated_at": expected_updated_at,
        }

        if shared_item_ids is not None:
            payload["shared_item_ids"] = shared_item_ids

        if status is not None:
            payload["status"] = status

        return await self._write(
            "PUT",
            f"/api/stats/live-orders/{table}",
            payload,
        )

    # ---------- แจ้งว่าระบบยืนยันการชำระครบแล้ว ----------

    async def mark_table_paid(
        self,
        table: int,
        paid_items: list[dict],
    ) -> bool:
        """เก็บโต๊ะเป็นชำระแล้ว จนกว่าพนักงานกดเคลียร์"""
        return await self._write(
            "POST",
            f"/api/stats/live-orders/{table}/paid",
            {
                "items": paid_items,
            },
        )

    # ---------- เรียกชำระ / แอดมินยืนยันรับเงิน ----------

    async def update_table_payment(
        self,
        table: int,
        opened_at: str,
        items: list[dict],
        action: str,
        method: str | None = None,
        expected_total: float | None = None,
    ) -> dict:
        """
        action:
            request-payment = เปลี่ยนเป็นรอชำระ
            confirm-payment = ยืนยันรับเงินครบทั้งโต๊ะ
        """
        async with httpx.AsyncClient(
            timeout=10.0
        ) as client:
            response = await client.post(
                (
                    f"{self.backend_url}"
                    f"/api/stats/live-orders/{table}/{action}"
                ),
                headers={
                    "X-Food-Kub-Key": admin_api_key(),
                },
                json={
                    "opened_at": opened_at,
                    "items": items,
                    "method": method,
                    "expected_total": expected_total,
                },
            )

            response.raise_for_status()
            return response.json()

    # ---------- เคลียร์โต๊ะ ----------

    async def reset_table(
        self,
        table: int,
        opened_at: str,
    ) -> dict:
        """
        เคลียร์โต๊ะที่ชำระครบแล้ว
        ส่ง opened_at เพื่อป้องกันเคลียร์บิลของลูกค้ารอบใหม่
        """
        async with httpx.AsyncClient(
            timeout=10.0
        ) as client:
            response = await client.post(
                (
                    f"{self.backend_url}"
                    f"/api/stats/live-orders/{table}/reset"
                ),
                headers={
                    "X-Food-Kub-Key": admin_api_key(),
                },
                json={
                    "opened_at": opened_at,
                },
            )

            response.raise_for_status()
            return response.json()

    # ---------- เปลี่ยนสถานะอาหาร ----------

    async def set_kitchen_status(
        self,
        table: int,
        item_id: int,
        status: Literal["cooking", "ready", "served"],
        expected_qty: int,
        opened_at: str,
    ) -> dict:
        """
        cooking = กำลังทำ
        ready = พร้อมเสิร์ฟ
        served = เสิร์ฟแล้ว
        """
        async with httpx.AsyncClient(
            timeout=10.0
        ) as client:
            response = await client.put(
                (
                    f"{self.backend_url}"
                    f"/api/stats/live-orders/{table}"
                    f"/items/{item_id}/kitchen-status"
                ),
                headers={
                    "X-Food-Kub-Key": admin_api_key(),
                },
                json={
                    "status": status,
                    "expected_qty": expected_qty,
                    "opened_at": opened_at,
                },
            )

            response.raise_for_status()
            return response.json()

    # ---------- อ่านข้อมูล Dashboard ----------

    async def get_dashboard(self) -> dict:
        async with httpx.AsyncClient(
            timeout=10.0
        ) as client:
            response = await client.get(
                f"{self.backend_url}/api/stats/dashboard"
            )

            response.raise_for_status()
            return response.json()

    # ---------- เปิด/ปิดขายเมนู ----------

    async def set_availability(
        self,
        item_id: int,
        available: bool,
    ) -> bool:
        async with httpx.AsyncClient(
            timeout=10.0
        ) as client:
            response = await client.post(
                (
                    f"{self.backend_url}"
                    f"/api/stats/availability/{item_id}"
                ),
                headers={
                    "X-Food-Kub-Key": admin_api_key(),
                },
                json={
                    "available": available,
                },
            )

            if response.status_code == 404:
                return False

            response.raise_for_status()
            return True


# ---------- แปลงจำนวนอาหารเป็นรายการพร้อมชื่อและราคา ----------

async def build_lines(
    menu_service,
    quantities: dict,
) -> list[dict]:
    lines = []

    for item_id, qty in quantities.items():
        if int(qty) <= 0:
            continue

        menu_item = await menu_service.get_by_id(
            int(item_id)
        )

        if menu_item:
            lines.append({
                "id": menu_item.id,
                "name": menu_item.name,
                "price": menu_item.price,
                "qty": int(qty),
            })

    return lines