from fastapi import APIRouter, Request

from app.services.template_service import TemplateService

class CartRouter:
  """รับ request เกี่ยวกับหน้าตะกร้า
    หมายเหตุ: ตะกร้าเก็บอยู่ฝั่ง frontend (localStorage ผ่าน JS)
    เพราะโปรเจกต์นี้ทำเฉพาะฝั่ง frontend ยังไม่มี backend/DB จริง
    """
  def __init__(self, template_service: TemplateService):
        self.router = APIRouter()
        self.template_service = template_service
        self._register_routes()

  def _register_routes(self):
        self.router.add_api_route("/cart", self.show_cart, methods=["GET"])

  async def show_cart(self, request: Request):
        return self.template_service.render(
            request, "cart.html", {"title": "ตะกร้าของฉัน"}
        )