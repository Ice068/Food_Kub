import logging

import httpx
from fastapi import APIRouter, Depends, Request, Form
from fastapi.responses import RedirectResponse

from app.core.table_context import set_table_context, table_query
from app.services.template_service import TemplateService
from app.services.cart_service import CartService
from app.services.menu_service import MenuService
from app.services.stats_service import StatsService, build_lines

logger = logging.getLogger(__name__)


class CartRouter:

    def __init__(
        self,
        cart_service: CartService,
        menu_service: MenuService,
        template_service: TemplateService,
        stats_service: StatsService,
    ):
        self.router = APIRouter(
            dependencies=[Depends(set_table_context)]
        )

        self.cart_service = cart_service
        self.menu_service = menu_service
        self.template_service = template_service
        self.stats_service = stats_service

        self._register_routes()

    def _register_routes(self):
        self.router.add_api_route(
            "/cart", self.show_cart, methods=["GET"]
        )
        self.router.add_api_route(
            "/cart/add/{item_id}", self.add_to_cart, methods=["POST"]
        )
        self.router.add_api_route(
            "/cart/update/{item_id}", self.update_cart, methods=["POST"]
        )
        self.router.add_api_route(
            "/cart/remove/{item_id}", self.remove_item, methods=["POST"]
        )
        self.router.add_api_route(
            "/cart/clear", self.clear_cart, methods=["POST"]
        )
        self.router.add_api_route(
            "/cart/send-to-kitchen",
            self.send_to_kitchen,
            methods=["POST"],
        )

    async def show_cart(
        self,
        request: Request,
        ordered: int | None = None,
    ):
        cart = self.cart_service.get_cart(request)
        cart_items = []
        total = 0.0

        for item_id, qty in cart.items():
            menu_item = await self.menu_service.get_by_id(int(item_id))

            if menu_item:
                total += menu_item.price * qty
                cart_items.append({
                    "id": menu_item.id,
                    "name": menu_item.name,
                    "price": menu_item.price,
                    "qty": qty,
                })

        active_orders = self.cart_service.get_active_orders(request)
        kitchen_items = []
        kitchen_total = 0.0

        for item_id, qty in active_orders.items():
            menu_item = await self.menu_service.get_by_id(int(item_id))

            if menu_item:
                kitchen_total += menu_item.price * qty
                kitchen_items.append({
                    "id": menu_item.id,
                    "name": menu_item.name,
                    "price": menu_item.price,
                    "qty": qty,
                })

        return self.template_service.render(
            request,
            "cart.html",
            {
                "title": "ตะกร้าของฉัน",
                "cart_items": cart_items,
                "total": total,
                "kitchen_items": kitchen_items,
                "kitchen_total": kitchen_total,
                "ordered": ordered == 1,
                "cart_count": self.cart_service.total_count(request),
                "bill_count": self.cart_service.bill_total_count(request),
            },
        )

    async def send_to_kitchen(self, request: Request):
        # เก็บเฉพาะรายการรอบนี้ก่อนตะกร้าถูกล้าง
        new_quantities = dict(self.cart_service.get_cart(request))

        if not new_quantities:
            return RedirectResponse(
                url=f"/cart{table_query(request)}",
                status_code=303,
            )

        self.cart_service.send_cart_to_kitchen(request)

        # รายการสะสมหลังส่งครัว รวมออเดอร์รอบก่อนด้วย
        active_quantities = dict(
            self.cart_service.get_active_orders(request)
        )
        table_id = getattr(request.state, "table_id", None)

        # StatsService จัดการ HTTP error ตอนเขียนข้อมูลเอง
        # ส่วนนี้รองรับ HTTP error ตอนดึงชื่อและราคาเมนู
        try:
            new_items = await build_lines(
                self.menu_service,
                new_quantities,
            )
            await self.stats_service.record_order(
                table_id,
                new_items,
            )

            if table_id is not None:
                active_items = await build_lines(
                    self.menu_service,
                    active_quantities,
                )
                await self.stats_service.sync_live_order(
                    table_id,
                    active_items,
                    status="dining",
                )
        except httpx.HTTPError:
            logger.exception(
                "ส่งครัวแล้ว แต่ดึงข้อมูลเมนูเพื่อบันทึกสถิติไม่สำเร็จ"
            )

        t_query = table_query(request)
        delim = "&" if t_query else "?"

        return RedirectResponse(
            url=f"/cart{t_query}{delim}ordered=1",
            status_code=303,
        )

    async def add_to_cart(
        self,
        request: Request,
        item_id: int,
    ):
        self.cart_service.add_item(request, item_id)

        return RedirectResponse(
            url=f"/cart{table_query(request)}",
            status_code=303,
        )

    async def update_cart(
        self,
        request: Request,
        item_id: int,
        quantity: int = Form(...),
    ):
        self.cart_service.update_quantity(
            request,
            item_id,
            quantity,
        )

        return RedirectResponse(
            url=f"/cart{table_query(request)}",
            status_code=303,
        )

    async def remove_item(
        self,
        request: Request,
        item_id: int,
    ):
        self.cart_service.remove_item(request, item_id)

        return RedirectResponse(
            url=f"/cart{table_query(request)}",
            status_code=303,
        )

    def clear_cart(self, request: Request):
        # ล้างเฉพาะรายการที่ยังไม่ได้ส่งครัว
        self.cart_service.clear(request)

        return RedirectResponse(
            url=f"/cart{table_query(request)}",
            status_code=303,
        )
