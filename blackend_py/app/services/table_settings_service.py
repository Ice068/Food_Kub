from datetime import datetime, timezone

from app.core.config import settings
from app.core.db import db

MAX_TABLES = 100


class TableSettingsService:
    """เก็บจำนวนโต๊ะของร้านใน Firestore
    ใช้ค่าเดียวกันทั้งหน้าสร้าง QR และ Dashboard
    """

    def __init__(self):
        self.ref = (
            db.collection("restaurant_settings")
            .document("tables")
        )

    def get_count(self) -> int:
        """อ่านจำนวนโต๊ะที่บันทึกไว้
        หากยังไม่ได้ตั้งค่า ใช้ TOTAL_TABLES จาก config เดิม
        """
        snapshot = self.ref.get()
        data = snapshot.to_dict() or {}

        count = data.get(
            "table_count",
            settings.TOTAL_TABLES,
        )

        if type(count) is not int or not 1 <= count <= MAX_TABLES:
            raise ValueError("Invalid stored table count")

        return count

    def set_count(self, count: int) -> int:
        """บันทึกจำนวนโต๊ะ โดยไม่ลบบิลหรือประวัติการชำระเงิน"""
        if type(count) is not int or not 1 <= count <= MAX_TABLES:
            raise ValueError("Table count must be between 1 and 100")

        self.ref.set(
            {
                "table_count": count,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            },
            merge=True,
        )

        return count