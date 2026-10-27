import httpx

from fastapi import APIRouter, Request, Form
from fastapi.responses import RedirectResponse
from urllib.parse import quote

from app.services.template_service import TemplateService
from app.services.cart_service import CartService
from app.services.menu_service import MenuService
from app.services.dashboard_service import DashboardService


class CartRouter:

    def __init__(
        self,
        cart_service: CartService,
        menu_service: MenuService,
        template_service: TemplateService,
        dashboard_service: DashboardService | None = None,
    ):
        self.router = APIRouter()

        self.cart_service = cart_service
        self.menu_service = menu_service
        self.template_service = template_service
        self.dashboard_service = dashboard_service or DashboardService()

        self._register_routes()

    def _register_routes(self):

        self.router.add_api_route(
            "/cart",
            self.show_cart,
            methods=["GET"]
        )

        self.router.add_api_route(
            "/cart/add/{item_id}",
            self.add_to_cart,
            methods=["POST"]
        )

        self.router.add_api_route(
            "/cart/update/{item_id}",
            self.update_cart,
            methods=["POST"]
        )

        self.router.add_api_route(
            "/cart/remove/{item_id}",
            self.remove_item,
            methods=["POST"]
        )

        self.router.add_api_route(
            "/cart/clear",
            self.clear_cart,
            methods=["POST"]
        )
        self.router.add_api_route("/cart/order", self.place_order, methods=["POST"])

    async def show_cart(self, request: Request):
        cart = self.cart_service.get_cart(request)

        cart_items = []
        total = 0

        for item_id, qty in cart.items():
            menu_item = await self.menu_service.get_by_id(int(item_id))

            if menu_item:
                total += menu_item.price * qty
                cart_items.append({
                    "id": menu_item.id,
                    "name": menu_item.name,
                    "price": menu_item.price,
                    "qty": qty
                })

        return self.template_service.render(
            request,
            "cart.html",
            {
                "title": "ตะกร้าของฉัน",
                "cart_items": cart_items,
                "total": total,
                "cart_count": self.cart_service.total_count(request),
                "table_number": request.session.get("table_number"),
                "error": request.query_params.get("error"),
            }
        )

    async def add_to_cart(
        self,
        request: Request,
        item_id: int
    ):
        item = await self.menu_service.get_by_id(item_id)
        if not item or not item.available:
            return RedirectResponse(url="/", status_code=303)
        self.cart_service.add_item(
            request,
            item_id
        )

        return RedirectResponse(
            url="/cart",
            status_code=303
        )

    async def update_cart(
        self,
        request: Request,
        item_id: int,
        quantity: int = Form(...)
    ):
        self.cart_service.update_quantity(
            request,
            item_id,
            quantity
        )

        return RedirectResponse(
            url="/cart",
            status_code=303
        )

    async def remove_item(
        self,
        request: Request,
        item_id: int
    ):
        self.cart_service.remove_item(
            request,
            item_id
        )

        return RedirectResponse(
            url="/cart",
            status_code=303
        )

    async def clear_cart(
        self,
        request: Request
    ):
        self.cart_service.clear(request)

        return RedirectResponse(
            url="/cart",
            status_code=303
        )

    async def place_order(self, request: Request, table_number: int = Form(0)):
        if not 1 <= table_number <= 30:
            return RedirectResponse(url="/cart?error=" + quote("กรุณาระบุหมายเลขโต๊ะ 1-30"), status_code=303)

        cart = self.cart_service.get_cart(request)
        order_items = []
        for item_id, qty in cart.items():
            item = await self.menu_service.get_by_id(int(item_id))
            if not item or not item.available:
                return RedirectResponse(url="/cart?error=" + quote("มีเมนูหมดหรือถูกลบ กรุณาตรวจสอบตะกร้า"), status_code=303)
            order_items.append({
                "id": item.id, "name": item.name, "category": item.category,
                "price": item.price, "qty": int(qty),
            })
        if not order_items:
            return RedirectResponse(url="/cart", status_code=303)
        try:
            await self.dashboard_service.place_order(table_number, order_items)
        except ValueError as exc:
            return RedirectResponse(url="/cart?error=" + quote(str(exc)), status_code=303)
        except httpx.HTTPError:
            return RedirectResponse(url="/cart?error=" + quote("เชื่อมต่อ Backend เพื่อบันทึกออเดอร์ไม่ได้"), status_code=303)
        request.session["table_number"] = table_number
        self.cart_service.clear(request)
        return RedirectResponse(url="/?table=" + str(table_number) + "&ordered=1", status_code=303)
