from starlette.requests import Request


class CartService:
    """Store each customer's carts in their session, scoped by the request's table."""

    SESSION_KEY = "cart"

    def _session_key(self, request: Request) -> str:
        table_id = getattr(request.state, "table_id", None)
        return f"cart_table_{table_id}" if table_id is not None else self.SESSION_KEY

    def get_cart(self, request: Request) -> dict:
        """คืนค่า cart เป็น dict {item_id(str): quantity(int)}"""
        return request.session.get(self._session_key(request), {})

    def add_item(self, request: Request, item_id: int):
        cart = self.get_cart(request)
        key = str(item_id)
        cart[key] = cart.get(key, 0) + 1
        request.session[self._session_key(request)] = cart

    def update_quantity(self, request: Request, item_id: int, quantity: int):
        cart = self.get_cart(request)
        key = str(item_id)
        if quantity <= 0:
            cart.pop(key, None)
        else:
            cart[key] = quantity
        request.session[self._session_key(request)] = cart

    def remove_item(self, request: Request, item_id: int):
        cart = self.get_cart(request)
        cart.pop(str(item_id), None)
        request.session[self._session_key(request)] = cart

    def deduct_items(self, request: Request, items_to_deduct: dict):
        """หักจำนวนรายการที่ชำระเงินแล้วออกจากตะกร้าของโต๊ะนั้น"""
        cart = self.get_cart(request)
        for item_id, qty in items_to_deduct.items():
            key = str(item_id)
            if key in cart:
                cart[key] -= int(qty)
                if cart[key] <= 0:
                    cart.pop(key, None)
        request.session[self._session_key(request)] = cart

    def clear(self, request: Request):
        request.session[self._session_key(request)] = {}

    def total_count(self, request: Request) -> int:
        return sum(self.get_cart(request).values())
