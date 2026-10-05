from typing import Literal

import httpx

from app.core.config import settings


class StatsService:
    """ส่งออเดอร์ เงินเข้า และบิลที่เปิดอยู่ไปเก็บที่ Backend
    พร้อมดึงสถิติมาแสดงบนแดชบอร์ด

    การส่งข้อมูลจาก flow ลูกค้าจะคืน False หากส่งไม่สำเร็จ
    ส่วนคำสั่งจาก Dashboard จะส่ง HTTP error ให้ Router จัดการ
    """

    def __init__(self):
        self.backend_url = settings.BACKEND_URL

    # ---------- เขียนข้อมูลออเดอร์และการชำระเงิน ----------

    async def _write(
        self,
        method: str,
        path: str,
        payload: dict,
    ) -> bool:
        """คืน False หากส่งข้อมูลไม่สำเร็จ เพื่อให้ flow ลูกค้าไปต่อได้"""
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
        payment_type: Literal["full", "split"] | None = None,
    ) -> bool:
        """ส่งรายการชำระเงินและรูปแบบการจ่าย

        full = บิลรวม
        split = แยกจ่ายรายคน
        None = ไม่ระบุรูปแบบ

        bill_closed เป็นสถานะปิดบิล แยกจากรูปแบบการจ่าย
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

        items ว่างยังทำให้โต๊ะว่างตามพฤติกรรมเดิม
        หลังชำระครบต้องใช้ mark_table_paid() แทน
        เพื่อเก็บโต๊ะไว้จนพนักงานกด Reset
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

    # ---------- ชำระครบ รอเคลียร์โต๊ะ ----------

    async def mark_table_paid(
        self,
        table: int,
        paid_items: list[dict],
    ) -> bool:
        """เรียกหลังยืนยันการชำระครบแล้ว

        ส่งรายการที่ชำระให้ Backend ตรวจสอบ
        และเก็บโต๊ะเป็น ชำระแล้ว · รอเคลียร์

        หากส่งไม่สำเร็จ คืน False เพื่อให้ผู้เรียกติดตามแก้ไข
        """
        return await self._write(
            "POST",
            f"/api/stats/live-orders/{table}/paid",
            {
                "items": paid_items,
            },
        )

    # ---------- Reset Table จาก Dashboard ----------

    async def reset_table(
        self,
        table: int,
        opened_at: str,
    ) -> dict:
        """เคลียร์โต๊ะหลังลูกค้าชำระครบและลุกออก

        opened_at ใช้ตรวจว่าบิลยังตรงกับที่พนักงานเปิดดู
        หากเคลียร์ไม่สำเร็จ ส่ง HTTP error ให้ DashboardRouter จัดการ
        """
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                f"{self.backend_url}/api/stats/live-orders/{table}/reset",
                json={
                    "opened_at": opened_at,
                },
            )

            resp.raise_for_status()
            return resp.json()

    # ---------- เปลี่ยนสถานะอาหาร ----------

    async def set_kitchen_status(
        self,
        table: int,
        item_id: int,
        status: Literal["cooking", "ready", "served"],
        expected_qty: int,
        opened_at: str,
    ) -> dict:
        """ส่งสถานะอาหารไปบันทึกที่ Backend

        cooking = กำลังทำ
        ready = พร้อมเสิร์ฟ
        served = เสิร์ฟแล้ว

        expected_qty และ opened_at ใช้ตรวจว่าบิลยังตรงกัน
        หากบันทึกไม่สำเร็จ ส่ง HTTP error ให้ DashboardRouter จัดการ
        """
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.put(
                (
                    f"{self.backend_url}/api/stats/live-orders/"
                    f"{table}/items/{item_id}/kitchen-status"
                ),
                json={
                    "status": status,
                    "expected_qty": expected_qty,
                    "opened_at": opened_at,
                },
            )

            resp.raise_for_status()
            return resp.json()

    # ---------- อ่านข้อมูล ----------

    async def get_dashboard(self) -> dict:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                f"{self.backend_url}/api/stats/dashboard"
            )

            resp.raise_for_status()
            return resp.json()

    # ---------- เปิด-ปิดขายเมนู ----------

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