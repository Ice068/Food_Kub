from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.services.menu_service import MenuService
from app.services.daily.stats_service import StatsService

router = APIRouter(prefix="/api/stats", tags=["Stats"])

stats_service = StatsService()
menu_service = MenuService()


# ---------- Payload ----------

class Line(BaseModel):
    id: int
    name: str
    price: float
    qty: int = Field(..., gt=0)


class OrderPayload(BaseModel):
    table: int | None = None
    items: list[Line]


class TransactionPayload(BaseModel):
    table: int | None = None
    method: str
    amount: float = Field(..., gt=0)
    items: list[Line]
    bill_closed: bool


class LiveOrderPayload(BaseModel):
    items: list[Line]
    status: Literal["dining", "waiting_payment"] | None = None


class AvailabilityPayload(BaseModel):
    available: bool


class KitchenStatusPayload(BaseModel):
    status: Literal["cooking", "ready", "served"]
    expected_qty: int = Field(..., gt=0)
    opened_at: str = Field(..., min_length=1)


class PaidTablePayload(BaseModel):
    items: list[Line] = Field(..., min_length=1)


class ResetTablePayload(BaseModel):
    opened_at: str = Field(..., min_length=1)


# ---------- บันทึกออเดอร์ ----------

@router.post("/orders")
async def record_order(payload: OrderPayload):
    stats_service.record_order(
        payload.table,
        [item.model_dump() for item in payload.items],
    )

    return {"status": "success"}


# ---------- บันทึกการชำระเงิน ----------

@router.post("/transactions")
async def record_transaction(payload: TransactionPayload):
    tx = stats_service.record_transaction(
        payload.table,
        payload.method,
        payload.amount,
        [item.model_dump() for item in payload.items],
        payload.bill_closed,
    )

    return {
        "status": "success",
        "id": tx["id"],
    }


# ---------- อัปเดตบิลและสถานะโต๊ะ ----------

@router.put("/live-orders/{table}")
async def set_live_order(
    table: int,
    payload: LiveOrderPayload,
):
    stats_service.set_live_order(
        table,
        [item.model_dump() for item in payload.items],
        payload.status,
    )

    return {"status": "success"}


# ---------- อัปเดตสถานะอาหาร ----------

@router.put(
    "/live-orders/{table}/items/{item_id}/kitchen-status",
    responses={
        404: {
            "description": "Order item not found",
        },
        409: {
            "description": "Table bill or order quantity has changed",
        },
    },
)
async def set_kitchen_status(
    table: int,
    item_id: int,
    payload: KitchenStatusPayload,
):
    try:
        item = stats_service.set_kitchen_status(
            table,
            item_id,
            payload.status,
            payload.expected_qty,
            payload.opened_at,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=409,
            detail=str(exc),
        ) from exc

    if item is None:
        raise HTTPException(
            status_code=404,
            detail="Order item not found",
        )

    return {
        "status": "success",
        "item": item,
    }


# ---------- ชำระครบ รอพนักงานเคลียร์โต๊ะ ----------

@router.post(
    "/live-orders/{table}/paid",
    responses={
        409: {
            "description": "New unpaid orders exist",
        },
    },
)
async def mark_table_paid(
    table: int,
    payload: PaidTablePayload,
):
    """เรียกหลังยืนยันว่าชำระครบแล้วเท่านั้น"""
    try:
        stats_service.mark_table_paid(
            table,
            [item.model_dump() for item in payload.items],
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=409,
            detail=str(exc),
        ) from exc

    return {"status": "success"}


# ---------- Reset Table ----------

@router.post(
    "/live-orders/{table}/reset",
    responses={
        404: {
            "description": "Table already free",
        },
        409: {
            "description": (
                "Table bill has changed or table is not fully paid"
            ),
        },
    },
)
async def reset_table(
    table: int,
    payload: ResetTablePayload,
):
    """เคลียร์โต๊ะที่ชำระครบแล้ว โดยเก็บประวัติยอดขายไว้"""
    try:
        reset = stats_service.reset_table(
            table,
            payload.opened_at,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=409,
            detail=str(exc),
        ) from exc

    if not reset:
        raise HTTPException(
            status_code=404,
            detail="Table already free",
        )

    return {
        "status": "success",
        "table": table,
    }


# ---------- ข้อมูล Dashboard ----------

@router.get("/dashboard")
async def get_dashboard():
    return stats_service.get_dashboard()


# ---------- เปิด/ปิดขายเมนู ----------

@router.post(
    "/availability/{item_id}",
    responses={
        404: {
            "description": "Menu item not found",
        },
    },
)
async def set_availability(
    item_id: int,
    payload: AvailabilityPayload,
):
    item = menu_service.set_availability(
        item_id,
        payload.available,
    )

    if item is None:
        raise HTTPException(
            status_code=404,
            detail="Menu item not found",
        )

    return {
        "status": "success",
        "item": item.to_dict(),
    }