import base64
import io

import qrcode

from app.services.payments.base import PaymentStrategy


class QrBankPaymentStrategy(PaymentStrategy):
    """วิธีจ่ายเงินแบบสแกน QR Code พร้อมเพย์ (PromptPay)

    สร้าง QR ตามมาตรฐาน EMVCo ที่ธนาคารไทยใช้จริง
    สแกนด้วยแอปธนาคารแล้วจำนวนเงินจะเด้งขึ้นมาอัตโนมัติ
    """

    AID_PROMPTPAY = "A000000677010111"   # รหัสประจำระบบพร้อมเพย์
    CURRENCY_THB = "764"                 # รหัสสกุลเงินบาท ตาม ISO 4217
    COUNTRY_TH = "TH"

    def __init__(self, promptpay_id: str):
        self.promptpay_id = promptpay_id

    def get_method_id(self) -> str:
        return "qr_bank"

    def get_display_name(self) -> str:
        return "สแกน QR Code พร้อมเพย์"

    def process(self, amount: float, items: list[dict]) -> dict:
        payload = self._build_promptpay_payload(amount)
        return {
            "status": "pending",
            "method": self.get_method_id(),
            "method_name": self.get_display_name(),
            "amount": amount,
            "message": f"สแกน QR Code เพื่อชำระเงิน {amount:,.2f} บาท",
            "qr_image": self._generate_qr_base64(payload),
        }

    # ---------- ส่วนสร้างข้อมูลใน QR ----------

    def _build_promptpay_payload(self, amount: float) -> str:
        """ประกอบข้อความในตัว QR ตามรูปแบบ TLV (tag-length-value)"""
        tag, target = self._normalize_promptpay_id()

        merchant = self._tlv("00", self.AID_PROMPTPAY) + self._tlv(tag, target)
        merchant_info = self._tlv("29", merchant)

        payload = (
            self._tlv("00", "01")                      # เวอร์ชันรูปแบบข้อมูล
            + self._tlv("01", "12")                    # 12 = QR ใช้ครั้งเดียว (ระบุจำนวนเงิน)
            + merchant_info                            # ข้อมูลบัญชีผู้รับเงิน
            + self._tlv("53", self.CURRENCY_THB)
            + self._tlv("54", f"{amount:.2f}")         # จำนวนเงิน
            + self._tlv("58", self.COUNTRY_TH)
            + "6304"                                   # tag 63 ยาว 4 = ค่าตรวจสอบความถูกต้อง
        )
        return payload + self._crc16(payload)

    def _normalize_promptpay_id(self) -> tuple[str, str]:
        """แปลงเลขพร้อมเพย์ให้อยู่ในรูปที่ QR ต้องการ พร้อมบอกว่าเป็นเลขประเภทไหน"""
        digits = "".join(ch for ch in self.promptpay_id if ch.isdigit())

        if len(digits) == 10 and digits.startswith("0"):
            return "01", "0066" + digits[1:]   # เบอร์มือถือ 08x -> 00668x
        if len(digits) == 13:
            return "02", digits                # เลขบัตรประชาชน / เลขนิติบุคคล
        if len(digits) == 15:
            return "03", digits                # เลขกระเป๋าเงินอิเล็กทรอนิกส์

        raise ValueError(f"เลขพร้อมเพย์ไม่ถูกต้อง: {self.promptpay_id}")

    @staticmethod
    def _tlv(tag: str, value: str) -> str:
        """ต่อข้อมูล 1 ช่องเป็นรูปแบบ tag + ความยาว 2 หลัก + ค่า"""
        return f"{tag}{len(value):02d}{value}"

    @staticmethod
    def _crc16(data: str) -> str:
        """คำนวณค่าตรวจสอบความถูกต้อง CRC-16/CCITT-FALSE ปิดท้าย QR"""
        crc = 0xFFFF
        for byte in data.encode("ascii"):
            crc ^= byte << 8
            for _ in range(8):
                if crc & 0x8000:
                    crc = (crc << 1) ^ 0x1021
                else:
                    crc <<= 1
                crc &= 0xFFFF
        return f"{crc:04X}"

    # ---------- ส่วนวาดรูป QR ----------

    @staticmethod
    def _generate_qr_base64(payload: str) -> str:
        """วาด QR เป็นรูป PNG แล้วแปลงเป็นข้อความ base64 ให้ฝังในหน้าเว็บได้เลย"""
        qr = qrcode.QRCode(version=None, box_size=8, border=2)
        qr.add_data(payload)
        qr.make(fit=True)

        img = qr.make_image(fill_color="black", back_color="white")
        buffer = io.BytesIO()
        img.save(buffer, format="PNG")
        return base64.b64encode(buffer.getvalue()).decode("ascii")
