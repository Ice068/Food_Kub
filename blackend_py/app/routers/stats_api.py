from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.services.stats_service import StatsService


router = APIRouter(prefix="/api/stats", tags=["Stats"])
stats_service = StatsService()


class OrderLine(BaseModel):
    id: int
    name: str
    category: str = "อื่นๆ"
    price: float = Field(ge=0)
    qty: int = Field(gt=0)


class OrderPayload(BaseModel):
    table: int = Field(ge=1, le=30)
    items: list[OrderLine] = Field(min_length=1)


class TableStatusPayload(BaseModel):
    status: str


class KitchenStatusPayload(BaseModel):
    status: str


class PaymentPayload(BaseModel):
    method: str


@router.post("/orders")
def place_order(payload: OrderPayload):
    try:
        return stats_service.place_order(payload.table, [item.model_dump() for item in payload.items])
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("/dashboard")
def dashboard_data():
    return stats_service.dashboard_data()


@router.put("/live-orders/{table}/status")
def set_table_status(table: int, payload: TableStatusPayload):
    try:
        return stats_service.set_table_status(table, payload.status)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.put("/live-orders/{table}/items/{item_id}/kitchen")
def set_kitchen_status(table: int, item_id: int, payload: KitchenStatusPayload):
    try:
        return stats_service.set_kitchen_status(table, item_id, payload.status)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/live-orders/{table}/pay")
def record_payment(table: int, payload: PaymentPayload):
    try:
        return stats_service.record_payment(table, payload.method)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/live-orders/{table}/reset")
def reset_table(table: int):
    try:
        return stats_service.reset_table(table)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
