from starlette.requests import Request


class CartService:
    """จัดการตะกร้าสินค้า เก็บไว้ใน session ของแต่ละคน (ฝั่ง server ไม่ใช้ JS)"""

    SESSION_KEY = "cart"

    def get_cart(self, request: Request) -> dict:
        """คืนค่า cart เป็น dict {item_id(str): quantity(int)}"""
        return request.session.get(self.SESSION_KEY, {})

    def add_item(self, request: Request, item_id: int):
        cart = self.get_cart(request)
        key = str(item_id)
        cart[key] = cart.get(key, 0) + 1
        request.session[self.SESSION_KEY] = cart

    def update_quantity(self, request: Request, item_id: int, quantity: int):
        cart = self.get_cart(request)
        key = str(item_id)
        if quantity <= 0:
            cart.pop(key, None)
        else:
            cart[key] = quantity
        request.session[self.SESSION_KEY] = cart

    def remove_item(self, request: Request, item_id: int):
        cart = self.get_cart(request)
        cart.pop(str(item_id), None)
        request.session[self.SESSION_KEY] = cart

    def clear(self, request: Request):
        request.session[self.SESSION_KEY] = {}

    def total_count(self, request: Request) -> int:
        return sum(self.get_cart(request).values())