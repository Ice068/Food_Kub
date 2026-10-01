class Settings:
    APP_TITLE: str = "ระบบหลังบ้าน Food_Kub (Backend API)"

    # เลขพร้อมเพย์ของร้าน (เบอร์มือถือ 10 หลัก / เลขบัตรประชาชน 13 หลัก)
    # ใช้สร้าง QR Code รับเงิน -- เปลี่ยนเป็นเลขของร้านจริงก่อนใช้งาน
    PROMPTPAY_ID: str = "0950927227"


settings = Settings()
