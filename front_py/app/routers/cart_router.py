import httpx

from fastapi import APIRouter, Depends, Form, Request, HTTPException
from fastapi.responses import RedirectResponse, JSONResponse

from app.core.table_context import set_table_context, table_query
from app.core.config import settings
from app.services.cart_service import CartService
from app.services.menu_service import MenuService
from app.services.stats_service import StatsService, build_lines
from app.services.template_service import TemplateService


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
        self.router.add_api_route("/cart/state", self.cart_state, methods=["GET"])
        self.router.add_api_route(
            "/cart",
            self.show_cart,
            methods=["GET"],
        )

        self.router.add_api_route(
            "/cart/add/{item_id}",
            self.add_to_cart,
            methods=["POST"],
        )

        self.router.add_api_route(
            "/cart/update/{item_id}",
            self.update_cart,
            methods=["POST"],
        )

        self.router.add_api_route(
            "/cart/remove/{item_id}",
            self.remove_item,
            methods=["POST"],
        )

        self.router.add_api_route(
            "/cart/clear",
            self.clear_cart,
            methods=["POST"],
        )

        self.router.add_api_route(
            "/cart/send-to-kitchen",
            self.send_to_kitchen,
            methods=["POST"],
        )

    # ---------- หน้าตะกร้า ----------

    async def show_cart(
        self,
        request: Request,
        ordered: int | None = None,
    ):
        cart = self.cart_service.get_cart(request)
        cart_items = []
        total = 0.0

        for item_id, qty in cart.items():
            menu_item = await self.menu_service.get_by_id(
                int(item_id)
            )

            if menu_item:
                total += menu_item.price * qty

                cart_items.append({
                    "id": menu_item.id,
                    "name": menu_item.name,
                    "price": menu_item.price,
                    "qty": qty,
                    "image_url": menu_item.image_url,
                    "category": menu_item.category,
                })

        active_orders = self.cart_service.get_active_orders(
            request
        )

        kitchen_items = []
        kitchen_total = 0.0

        for item_id, qty in active_orders.items():
            menu_item = await self.menu_service.get_by_id(
                int(item_id)
            )

            if menu_item:
                kitchen_total += menu_item.price * qty

                kitchen_items.append({
                    "id": menu_item.id,
                    "name": menu_item.name,
                    "price": menu_item.price,
                    "qty": qty,
                    "image_url": menu_item.image_url,
                    "category": menu_item.category,
                })

        shared_paid = float(self.cart_service.get_shared_paid(request))
        remaining_kitchen_total = max(0.0, kitchen_total - shared_paid)

        return self.template_service.render(
            request,
            "cart.html",
            {
                "title": "ตะกร้าของฉัน",
                "cart_items": cart_items,
                "total": total,
                "kitchen_items": kitchen_items,
                "kitchen_total": kitchen_total,
                "shared_paid": shared_paid,
                "remaining_kitchen_total": remaining_kitchen_total,
                "ordered": ordered == 1,
                "cart_count": self.cart_service.total_count(
                    request
                ),
                "bill_count": self.cart_service.bill_total_count(
                    request
                ),
            },
        )

    # ---------- ส่งอาหารเข้าครัว ----------

    async def send_to_kitchen(self, request: Request):
        if getattr(request.state, "table_id", None) is None and not settings.DEMO_MODE:
            raise HTTPException(409, "กรุณาสแกน QR ที่โต๊ะก่อนส่งอาหารเข้าครัว รายการที่เลือกยังอยู่ในตะกร้า")
        new_quantities = dict(
            self.cart_service.get_cart(request)
        )

        if not new_quantities:
            return RedirectResponse(
                url=f"/cart{table_query(request)}",
                status_code=303,
            )

        for item_id, quantity in new_quantities.items():
            item = await self.menu_service.get_by_id(int(item_id))
            if not item or not item.available or not 1 <= quantity <= 99:
                raise HTTPException(409, "มีเมนูที่ไม่พร้อมจำหน่าย กรุณาตรวจสอบตะกร้าก่อนส่งครัว")

        active_quantities = dict(
            self.cart_service.get_active_orders(request)
        )

        for key, qty in new_quantities.items():
            active_quantities[key] = (
                active_quantities.get(key, 0) + qty
            )

        table_id = getattr(request.state, "table_id", None)

        try:
            if table_id is not None:
                active_items = await build_lines(
                    self.menu_service,
                    active_quantities,
                )

                live = (
                    getattr(request.state, "live_table", None)
                    or {}
                )

                synced = await self.stats_service.sync_live_order(
                    table_id,
                    active_items,
                    status="dining",
                    expected_opened_at=live.get("opened_at"),
                    expected_updated_at=live.get("updated_at"),
                )

                if not synced:
                    raise HTTPException(409, "บิลเปลี่ยนหรือส่งครัวไม่สำเร็จ กรุณากลับไปโหลดตะกร้าใหม่")

            # ล้างตะกร้าเมื่อบันทึกบิลสำเร็จแล้ว
            self.cart_service.send_cart_to_kitchen(request)

            new_items = await build_lines(
                self.menu_service,
                new_quantities,
            )

            await self.stats_service.record_order(
                table_id,
                new_items,
            )

        except httpx.HTTPError as exc:
            raise HTTPException(503, "ติดต่อครัวไม่ได้ กรุณาลองใหม่") from exc

        t_query = table_query(request)
        delim = "&" if t_query else "?"

        return RedirectResponse(
            url=f"/cart{t_query}{delim}ordered=1",
            status_code=303,
        )

    # ---------- เพิ่มอาหาร ----------

    async def add_to_cart(
        self,
        request: Request,
        item_id: int,
    ):
        item = await self.menu_service.get_by_id(item_id)
        if not item:
            raise HTTPException(404, "ไม่พบเมนูนี้")
        if not item.available:
            raise HTTPException(409, "เมนูนี้หมดชั่วคราว")
        if self.cart_service.get_cart(request).get(str(item_id), 0) >= 99:
            raise HTTPException(422, "สั่งได้สูงสุด 99 จานต่อเมนู")
        self.cart_service.add_item(request, item_id)
        if self._wants_json(request):
            return await self.cart_state(request, "เพิ่มลงตะกร้าแล้ว")

        return RedirectResponse(
            url=f"/cart{table_query(request)}",
            status_code=303,
        )

    # ---------- แก้จำนวน ----------

    async def update_cart(
        self,
        request: Request,
        item_id: int,
        quantity: int = Form(..., ge=0, le=99),
    ):
        item = await self.menu_service.get_by_id(item_id)
        if quantity > 0 and (not item or not item.available):
            raise HTTPException(409, "เมนูนี้ไม่พร้อมจำหน่าย")
        self.cart_service.update_quantity(
            request,
            item_id,
            quantity,
        )
        if self._wants_json(request):
            return await self.cart_state(request, "อัปเดตจำนวนแล้ว")

        return RedirectResponse(
            url=f"/cart{table_query(request)}",
            status_code=303,
        )

    # ---------- ลบอาหาร ----------

    async def remove_item(
        self,
        request: Request,
        item_id: int,
    ):
        self.cart_service.remove_item(request, item_id)
        if self._wants_json(request):
            return await self.cart_state(request, "นำออกจากตะกร้าแล้ว")

        return RedirectResponse(
            url=f"/cart{table_query(request)}",
            status_code=303,
        )

    # ---------- ล้างเฉพาะตะกร้าที่ยังไม่ส่งครัว ----------

    async def clear_cart(self, request: Request):
        self.cart_service.clear(request)
        if self._wants_json(request):
            return await self.cart_state(request, "ล้างตะกร้าแล้ว")

        return RedirectResponse(
            url=f"/cart{table_query(request)}",
            status_code=303,
        )
    @staticmethod
    def _wants_json(request: Request) -> bool:
        return "application/json" in request.headers.get("accept", "")

    async def cart_state(self, request: Request, message: str = ""):
        cart = dict(self.cart_service.get_cart(request))
        items = []
        for key, qty in cart.items():
            item = await self.menu_service.get_by_id(int(key))
            if item:
                items.append({**item.to_dict(), "qty": qty})
        return JSONResponse({"ok": True, "cart": cart, "items": items,
            "total": round(sum(item["price"] * item["qty"] for item in items), 2),
            "cart_count": self.cart_service.total_count(request),
            "bill_count": self.cart_service.bill_total_count(request), "message": message},
            headers={"Cache-Control": "no-store"})
