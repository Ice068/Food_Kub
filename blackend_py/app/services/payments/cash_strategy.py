import uuid

from app.services.payments.base import PaymentStrategy


class CashPaymentStrategy(PaymentStrategy):
    """วิธีจ่ายเงินแบบเงินสด (จ่ายที่หน้าร้าน)"""

    def get_method_id(self) -> str:
        return "cash"

    def get_display_name(self) -> str:
        return "เงินสด (จ่ายที่หน้าร้าน)"

    def process(self, amount: float, items: list[dict]) -> dict:
        return {
            "status": "success",
            "payment_id": f"cash-{uuid.uuid4().hex[:12]}",
            "method": self.get_method_id(),
            "method_name": self.get_display_name(),
            "amount": amount,
            "message": f"ชำระเงินสด {amount:,.2f} บาท เรียบร้อยแล้ว",
        }
