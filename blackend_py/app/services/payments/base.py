from abc import ABC, abstractmethod


class PaymentStrategy(ABC):
    """แม่แบบของทุกวิธีการจ่ายเงิน (Strategy Pattern)

    ทุกวิธีจ่ายเงินใหม่ที่จะเพิ่มเข้ามา ต้องสืบทอดคลาสนี้
    แล้วเขียน 3 เมธอดข้างล่างให้ครบ ระบบส่วนอื่นจะใช้งานได้ทันที
    """

    @abstractmethod
    def get_method_id(self) -> str:
        """รหัสของวิธีจ่ายเงิน ใช้อ้างอิงในระบบ เช่น "cash", "qr_bank" """

    @abstractmethod
    def get_display_name(self) -> str:
        """ชื่อที่แสดงให้ลูกค้าเห็น เช่น "เงินสด" """

    @abstractmethod
    def process(self, amount: float, items: list[dict]) -> dict:
        """ทำรายการจ่ายเงิน แล้วคืนผลลัพธ์เป็น dict ให้ client นำไปแสดง"""
