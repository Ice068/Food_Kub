from typing import Literal

import secrets

from fastapi import APIRouter, Depends, Header, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app.core.admin_auth import admin_api_key
from app.services.daily.stats_service import StatsService
from app.services.menu_service import MenuService


router = APIRouter(prefix="/api/stats", tags=["Stats"])

_admin_key = admin_api_key(create=True)


async def require_internal_admin(
    x_food_kub_key: str = Header(""),
):
    if not secrets.compare_digest(x_food_kub_key, _admin_key):
        raise HTTPException(
            status_code=401,
            detail="Internal admin authentication required",
        )


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

    # รูปแบบการชำระ: ทั้งบิลหรือแยกจ่ายรายคน
    payment_type: Literal["full", "split"] | None = None


class LiveOrderPayload(BaseModel):
    items: list[Line]
    status: Literal["dining", "waiting_payment"] | None = None
    shared_paid: float = Field(0, ge=0)
    shared_item_ids: list[int] = Field(default_factory=list)
    expected_opened_at: str | None = None
    expected_updated_at: str | None = None


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


class AdminTablePaymentPayload(BaseModel):
    opened_at: str = Field(..., min_length=1)
    items: list[Line] = Field(..., min_length=1)
    method: Literal["cash", "qr_bank"] | None = None
    expected_total: float = Field(
        ...,
        gt=0,
        allow_inf_nan=False,
    )


# ---------- บันทึกออเดอร์ ----------

@router.post(
    "/orders",
    dependencies=[Depends(require_internal_admin)],
)
async def record_order(payload: OrderPayload):
    stats_service.record_order(
        payload.table,
        [item.model_dump() for item in payload.items],
    )

    return {"status": "success"}


# ---------- บันทึกการชำระเงิน ----------

@router.post(
    "/transactions",
    dependencies=[Depends(require_internal_admin)],
)
async def record_transaction(payload: TransactionPayload):
    tx = stats_service.record_transaction(
        payload.table,
        payload.method,
        payload.amount,
        [item.model_dump() for item in payload.items],
        payload.bill_closed,
        payload.payment_type,
    )

    return {
        "status": "success",
        "id": tx["id"],
    }


# ---------- อ่านบิลโต๊ะ ----------

@router.get("/live-orders/{table}")
async def get_live_table(table: int):
    return {
        "table": stats_service.get_live_table(table),
    }


# ---------- อัปเดตบิลและสถานะโต๊ะ ----------

@router.put(
    "/live-orders/{table}",
    dependencies=[Depends(require_internal_admin)],
    responses={
        401: {
            "description": "Internal admin authentication required",
        },
        409: {
            "description": "Table bill or order state has changed",
        },
    },
)
async def set_live_order(
    table: int,
    payload: LiveOrderPayload,
):
    try:
        stats_service.set_live_order(
            table,
            [item.model_dump() for item in payload.items],
            payload.status,
            payload.shared_paid,
            payload.shared_item_ids,
            payload.expected_opened_at,
            payload.expected_updated_at,
        )

    except ValueError as exc:
        raise HTTPException(
            status_code=409,
            detail=str(exc),
        ) from exc

    return {"status": "success"}


# ---------- อัปเดตสถานะอาหาร ----------

@router.put(
    "/live-orders/{table}/items/{item_id}/kitchen-status",
    dependencies=[Depends(require_internal_admin)],
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


# ---------- เรียกชำระเงิน ----------

@router.post(
    "/live-orders/{table}/request-payment",
    dependencies=[Depends(require_internal_admin)],
    responses={
        401: {
            "description": "Internal admin authentication required",
        },
        404: {
            "description": "Table not found",
        },
        409: {
            "description": "Table bill or payment state has changed",
        },
    },
)
async def request_table_payment(
    table: int,
    payload: AdminTablePaymentPayload,
):
    return _update_table_payment(
        table,
        payload,
        "request-payment",
    )


# ---------- แอดมินยืนยันรับเงิน ----------

@router.post(
    "/live-orders/{table}/confirm-payment",
    dependencies=[Depends(require_internal_admin)],
    responses={
        401: {
            "description": "Internal admin authentication required",
        },
        404: {
            "description": "Table not found",
        },
        409: {
            "description": "Table bill or payment state has changed",
        },
    },
)
async def confirm_table_payment(
    table: int,
    payload: AdminTablePaymentPayload,
):
    return _update_table_payment(
        table,
        payload,
        "confirm-payment",
    )


def _update_table_payment(
    table: int,
    payload: AdminTablePaymentPayload,
    action: str,
):
    try:
        return stats_service.update_table_payment(
            table,
            payload.opened_at,
            [item.model_dump() for item in payload.items],
            action,
            payload.method,
            payload.expected_total,
        )

    except LookupError as exc:
        return JSONResponse(
            status_code=404,
            content={"detail": str(exc)},
        )

    except ValueError as exc:
        return JSONResponse(
            status_code=409,
            content={"detail": str(exc)},
        )


# ---------- ชำระครบ รอพนักงานเคลียร์โต๊ะ ----------

@router.post(
    "/live-orders/{table}/paid",
    dependencies=[Depends(require_internal_admin)],
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


# ---------- เคลียร์โต๊ะ ----------

@router.post(
    "/live-orders/{table}/reset",
    dependencies=[Depends(require_internal_admin)],
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
    """เคลียร์โต๊ะที่ชำระครบ โดยเก็บประวัติยอดขายไว้"""
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
    dependencies=[Depends(require_internal_admin)],
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