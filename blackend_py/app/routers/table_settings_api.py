import secrets
from fastapi import APIRouter, Header, HTTPException
from app.core.admin_auth import admin_api_key
from pydantic import BaseModel, Field

from app.services.table_settings_service import (
    MAX_TABLES,
    TableSettingsService,
)

router = APIRouter(
    prefix="/api/table-settings",
    tags=["Table Settings"],
)

table_settings = TableSettingsService()


class TableCountPayload(BaseModel):
    table_count: int = Field(
        ...,
        ge=1,
        le=MAX_TABLES,
        strict=True,
    )


@router.get("")
def get_table_settings():
    """อ่านจำนวนโต๊ะที่ใช้ร่วมกันทั้ง QR และ Dashboard"""
    return {
        "table_count": table_settings.get_count(),
        "max_tables": MAX_TABLES,
    }


@router.put("")
def save_table_settings(payload: TableCountPayload, x_food_kub_key: str | None = Header(None)):
    """บันทึกจำนวนโต๊ะของร้านลง Firestore"""
    if not x_food_kub_key or not secrets.compare_digest(x_food_kub_key, admin_api_key()):
        raise HTTPException(401, "Admin access required")
    count = table_settings.set_count(payload.table_count)

    return {
        "status": "success",
        "table_count": count,
    }
