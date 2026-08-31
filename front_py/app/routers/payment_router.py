import httpx
from fastapi import APIRouter, Request, Form
from fastapi.responses import RedirectResponse

from app.services.cart_service import CartService
from app.services.menu_service import MenuService
from app.services.payment_service import PaymentService
from app.services.template_service import TemplateService


class PaymentRouter:
    """รับ request หน้าชำระเงิน แล้วประสานงานระหว่างตะกร้ากับ PaymentService"""

    def __init__(
        self,
        payment_service: PaymentService,
        cart_service: CartService,
        menu_service: MenuService,
        template_service: TemplateService,
    ):
        self.router = APIRouter(prefix="/checkout")

        self.payment_service = payment_service
        self.cart_service = cart_service
        self.menu_service = menu_service
        self.template_service = template_service

        self._register_routes()

    def _register_routes(self):
        self.router.add_api_route("", self.show_checkout, methods=["GET"])
        self.router.add_api_route("/pay", self.process_payment, methods=["POST"])

    async def show_checkout(self, request: Request):
        """หน้าเลือกวิธีจ่ายเงิน พร้อมสรุปรายการที่สั่ง"""
        items, total = await self._build_order(request)

        # ตะกร้าว่าง ไม่มีอะไรให้จ่าย ส่งกลับไปหน้าตะกร้า
        if not items:
            return RedirectResponse(url="/cart", status_code=303)

        methods = await self.payment_service.get_methods()

        return self.template_service.render(
            request,
            "checkout.html",
            {
                "title": "ชำระเงิน",
                "items": items,
                "total": total,
                "methods": methods,
                "cart_count": self.cart_service.total_count(request),
            },
        )

    async def process_payment(self, request: Request, method: str = Form(...)):
        """ส่งคำสั่งจ่ายเงินไปหลังบ้าน แล้วแสดงผลลัพธ์ (ข้อความ หรือ QR Code)"""
        items, total = await self._build_order(request)

        if not items:
            return RedirectResponse(url="/cart", status_code=303)

        context = {
            "title": "ผลการชำระเงิน",
            "total": total,
            "cart_count": self.cart_service.total_count(request),
        }

        try:
            context["result"] = await self.payment_service.process(method, total, items)
        except httpx.HTTPStatusError:
            context["error"] = "ไม่สามารถทำรายการได้ กรุณาเลือกวิธีจ่ายเงินอีกครั้ง"
        except httpx.HTTPError:
            context["error"] = "ติดต่อเซิร์ฟเวอร์ชำระเงินไม่ได้ กรุณาลองใหม่"

        return self.template_service.render(request, "payment_result.html", context)

    # ---------- ตัวช่วยภายใน ----------

    async def _build_order(self, request: Request) -> tuple[list[dict], float]:
        """แปลงตะกร้าใน session เป็นรายการสั่งซื้อ + ยอดรวม"""
        cart = self.cart_service.get_cart(request)

        items = []
        total = 0.0

        for item_id, qty in cart.items():
            menu_item = await self.menu_service.get_by_id(int(item_id))
            if menu_item:
                total += menu_item.price * qty
                items.append({
                    "id": menu_item.id,
                    "name": menu_item.name,
                    "price": menu_item.price,
                    "qty": qty,
                })

        return items, total
