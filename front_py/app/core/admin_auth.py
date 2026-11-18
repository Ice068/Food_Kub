import os
from pathlib import Path

import httpx
from itsdangerous import URLSafeTimedSerializer, BadSignature
from app.core.config import settings


def admin_api_key() -> str:
    if settings.DEMO_MODE:
        return "local-demo-only"
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

def create_admin_token() -> str:
    return URLSafeTimedSerializer(settings.SESSION_SECRET, salt="food-kub-admin").dumps({"role": "admin"})


def valid_admin_token(token: str | None) -> bool:
    if not token:
        return False
    try:
        value = URLSafeTimedSerializer(settings.SESSION_SECRET, salt="food-kub-admin").loads(token, max_age=43200)
        return value == {"role": "admin"}
    except (BadSignature, TypeError):
        return False
