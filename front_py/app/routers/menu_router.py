import httpx
from fastapi import APIRouter, Depends, Form, Request

from app.core.table_context import set_table_context
from app.services.cart_service import CartService
from app.services.discovery_service import DiscoveryService
from app.services.menu_service import MenuService
from app.services.template_service import TemplateService


class MenuRouter:
    """รับ request เกี่ยวกับหน้าเมนู แล้วประสานงานกับ MenuService + TemplateService"""

    def __init__(
        self,
        menu_service: MenuService,
        template_service: TemplateService,
        cart_service: CartService,
    ):
        self.router = APIRouter(dependencies=[Depends(set_table_context)])
        self.menu_service = menu_service
        self.template_service = template_service
        self.cart_service = cart_service
        self.discovery = DiscoveryService()

        self._register_routes()

    def _register_routes(self):
        self.router.add_api_route("/", self.show_menu, methods=["GET"])
        self.router.add_api_route("/random", self.show_random, methods=["GET"])
        self.router.add_api_route("/random", self.spin_random, methods=["POST"])

        # รองรับชื่อหมวดที่มี / เช่น ทอด/ผัด
        self.router.add_api_route(
            "/category/{category:path}",
            self.show_by_category,
            methods=["GET"],
        )

    async def _catalog(self):
        try:
            menu_items = await self.menu_service.get_all()
            items = self.discovery.prepare_items(menu_items)
            return items, ""

        except httpx.HTTPError:
            return [], (
                "โหลดเมนูไม่สำเร็จ "
                "กรุณาตรวจสอบว่าเซิร์ฟเวอร์อาหารเปิดอยู่ แล้วลองใหม่"
            )

    def _render(self, request, template, context, error):
        context["cart_count"] = self.cart_service.total_count(request)
        context["error"] = error

        response = self.template_service.render(request, template, context)

        if error:
            response.status_code = 503

        response.headers["Cache-Control"] = "no-store"
        return response

    async def show_menu(self, request: Request):
        return await self._menu_page(request)

    async def show_by_category(self, request: Request, category: str):
        return await self._menu_page(request, category)

    async def _menu_page(self, request, category=""):
        all_items, error = await self._catalog()

        categories = list(
            dict.fromkeys(item["category"] for item in all_items)
        )

        items = (
            [item for item in all_items if item["category"] == category]
            if category
            else all_items
        )

        return self._render(
            request,
            "menu.html",
            {
                "title": f"เมนู: {category}" if category else "เมนูอาหาร",
                "items": items,
                "categories": categories,
                "selected_category": category,
                "recommended_items": (
                    self.discovery.recommendations(all_items)
                    if not category
                    else []
                ),
            },
            error,
        )

    async def show_random(self, request: Request, category: str = ""):
        return await self._random_page(request, category, False)

    async def spin_random(
        self,
        request: Request,
        category: str = Form(""),
    ):
        return await self._random_page(request, category, True)

    async def _random_page(self, request, category, spin):
        all_items, error = await self._catalog()

        categories = list(
            dict.fromkeys(item["category"] for item in all_items)
        )

        items = (
            [item for item in all_items if item["category"] == category]
            if category
            else all_items
        )

        context = self.discovery.build_wheel(items, spin=spin)
        context.update(
            {
                "title": "วันนี้กินอะไรดี?",
                "categories": categories,
                "selected_category": category,
                "spinning": spin and bool(items),
            }
        )

        return self._render(request, "random.html", context, error)