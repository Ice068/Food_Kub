from app.core.config import settings
from app.services.payments.base import PaymentStrategy
from app.services.payments.cash_strategy import CashPaymentStrategy
from app.services.payments.qr_bank_strategy import QrBankPaymentStrategy


class PaymentContext:
    """ตัวกลางเลือกวิธีจ่ายเงินตามค่า method ที่ลูกค้าส่งมา

    router ไม่ต้องรู้ว่าแต่ละวิธีทำงานอย่างไร คุยกับคลาสนี้ที่เดียว
    จะเพิ่มวิธีจ่ายเงินใหม่ก็แค่มาเติมใน _strategies
    """

    def __init__(self):
        strategies: list[PaymentStrategy] = [
            CashPaymentStrategy(),
            QrBankPaymentStrategy(settings.PROMPTPAY_ID),
        ]
        self._strategies: dict[str, PaymentStrategy] = {
            strategy.get_method_id(): strategy for strategy in strategies
        }

    def get_available_methods(self) -> list[dict]:
        """คืนรายชื่อวิธีจ่ายเงินที่เปิดใช้งาน ให้หน้าบ้านเอาไปแสดงเป็นตัวเลือก"""
        return [
            {"id": strategy.get_method_id(), "name": strategy.get_display_name()}
            for strategy in self._strategies.values()
        ]

    def process(self, method: str, amount: float, items: list[dict]) -> dict:
        strategy = self._strategies.get(method)
        if strategy is None:
            available = ", ".join(self._strategies.keys())
            raise ValueError(f"ไม่รองรับวิธีจ่ายเงิน: {method} (ที่รองรับ: {available})")
        return strategy.process(amount, items)
