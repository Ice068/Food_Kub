import os
from pathlib import Path

import httpx


def admin_api_key() -> str:
    configured = os.environ.get("FOOD_KUB_ADMIN_API_KEY")
    if configured:
        return configured

    # อ่านกุญแจเดียวกับที่ Backend สร้างไว้ที่ root โปรเจกต์
    path = Path(__file__).resolve().parents[3] / ".food_kub_admin_key"

    try:
        return path.read_text(encoding="utf-8").strip()
    except OSError as exc:
        raise httpx.ConnectError(
            "ไม่พบกุญแจภายใน กรุณาเริ่ม Backend ก่อน Frontend"
        ) from exc