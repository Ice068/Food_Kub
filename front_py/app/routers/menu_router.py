from fastapi import APIRouter, Request

from app.services.menu_service import MenuService
from app.services.template_service import TemplateService
from app.services.cart_service import CartService  # เพิ่มบรรทัดนี้


class MenuRouter:
    """รับ request เกี่ยวกับหน้าเมนู แล้วประสานงานกับ MenuService + TemplateService"""

    def __init__(self, menu_service: MenuService, template_service: TemplateService, cart_service: CartService):
        self.router = APIRouter()
        self.menu_service = menu_service
        self.template_service = template_service
        self.cart_service = cart_service  # เพิ่มบรรทัดนี้
        self._register_routes()

    def _register_routes(self):
        self.router.add_api_route("/", self.show_menu, methods=["GET"])
        self.router.add_api_route("/category/{category}", self.show_by_category, methods=["GET"])

    async def show_menu(self, request: Request):
        items = [item.to_dict() for item in self.menu_service.get_all()]
        categories = self.menu_service.get_categories()
        return self.template_service.render(
            request,
            "menu.html",
            {
                "title": "เมนูอาหาร",
                "items": items,
                "categories": categories,
                "cart_count": self.cart_service.total_count(request),  # เพิ่มบรรทัดนี้
            },
        )

    async def show_by_category(self, request: Request, category: str):
        items = [item.to_dict() for item in self.menu_service.get_by_category(category)]
        categories = self.menu_service.get_categories()
        return self.template_service.render(
            request,
            "menu.html",
            {
                "title": f"เมนู: {category}",
                "items": items,
                "categories": categories,
                "cart_count": self.cart_service.total_count(request),  # เพิ่มบรรทัดนี้
            },
        )