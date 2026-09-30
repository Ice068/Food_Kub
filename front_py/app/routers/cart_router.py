from fastapi import APIRouter, Request, Form
from fastapi.responses import RedirectResponse

from app.services.template_service import TemplateService
from app.services.cart_service import CartService
from app.services.menu_service import MenuService


class CartRouter:

    def __init__(
        self,
        cart_service: CartService,
        menu_service: MenuService,
        template_service: TemplateService
    ):
        self.router = APIRouter()

        self.cart_service = cart_service
        self.menu_service = menu_service
        self.template_service = template_service

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
                "cart_count": self.cart_service.total_count(request)
            }
        )

    async def add_to_cart(
        self,
        request: Request,
        item_id: int
    ):
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