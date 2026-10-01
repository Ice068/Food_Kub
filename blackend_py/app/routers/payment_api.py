from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.services.payments.payment_context import PaymentContext

router = APIRouter(prefix="/api/payment", tags=["Payment"])
payment_context = PaymentContext()


class OrderItem(BaseModel):
    id: int
    name: str
    price: float
    qty: int


class PaymentRequest(BaseModel):
    method: str = Field(..., description="cash หรือ qr_bank")
    amount: float = Field(..., gt=0)
    items: list[OrderItem]


@router.get("/methods")
async def get_payment_methods():
    return payment_context.get_available_methods()


@router.post("/process")
async def process_payment(request: PaymentRequest):
    try:
        items = [item.model_dump() for item in request.items]
        return payment_context.process(request.method, request.amount, items)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
