from fastapi import APIRouter
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
def save_table_settings(payload: TableCountPayload):
    """บันทึกจำนวนโต๊ะของร้านลง Firestore"""
    count = table_settings.set_count(payload.table_count)

    return {
        "status": "success",
        "table_count": count,
    }