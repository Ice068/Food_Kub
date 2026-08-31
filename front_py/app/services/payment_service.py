import httpx

from app.core.config import settings


class PaymentService:
    """คุยกับ API จ่ายเงินของเซิร์ฟเวอร์ Backend (blackend_py)

    หน้าบ้านไม่รู้วิธีสร้าง QR หรือกฎการจ่ายเงินเลย
    หน้าที่ของคลาสนี้คือส่งคำขอไปถามหลังบ้านแล้วเอาคำตอบกลับมา
    """

    def __init__(self):
        self.backend_url = settings.BACKEND_URL

    async def get_methods(self) -> list[dict]:
        """ดึงรายชื่อวิธีจ่ายเงินที่เปิดใช้งาน"""
        async with httpx.AsyncClient() as client:
            resp = await client.get(f"{self.backend_url}/api/payment/methods")
            resp.raise_for_status()
            return resp.json()

    async def process(self, method: str, amount: float, items: list[dict]) -> dict:
        """ส่งคำสั่งจ่ายเงินไปให้หลังบ้านทำรายการ"""
        payload = {"method": method, "amount": amount, "items": items}
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{self.backend_url}/api/payment/process", json=payload
            )
            resp.raise_for_status()
            return resp.json()
